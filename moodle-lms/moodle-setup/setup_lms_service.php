<?php
// One-time, idempotent Moodle configuration for the My Coach LMS student app.
//
// What it does (and nothing else):
//   1. Creates the external service "My Coach LMS" (shortname mycoach_lms) with ONLY the
//      student-facing functions the LMS app calls. Tokens for it are issued per student through
//      Moodle's own login/token.php, so every call runs AS that student and Moodle enforces
//      that a student only ever sees their own courses, submissions, attempts and grades.
//   2. Creates the system role "My Coach LMS student" (moodle/webservice:createtoken +
//      webservice/rest:use) and assigns it to the SYNTHETIC student accounts only
//      (username s6900NN whose idnumber is the matching student ID 6900NN).
//   3. Enables file submissions (in addition to the existing online text) on the assignments of
//      the synthetic "Fall 2026" category, so students can upload a file.
//   4. Sets the sign-in password of the synthetic student accounts to the value of the
//      environment variable LMS_STUDENT_TEST_PASSWORD (their previous passwords were random
//      and unknown, so nobody could sign in as them).
//   5. Creates a lookup-only web service account (mycoach_lms_lookup, auth "webservice", one
//      function: core_user_get_users_by_field) so the LMS can turn a student ID into the Moodle
//      username at sign-in, and writes its token to the file named by LMS_LOOKUP_TOKEN_FILE.
//
// It never deletes anything, never touches courses/grades/submissions/attempts and creates no
// student or teacher accounts. Running it again only fills in what is missing.
//
// Usage (with Moodle's bundled PHP):
//   set LMS_STUDENT_TEST_PASSWORD=...        (PowerShell: $env:LMS_STUDENT_TEST_PASSWORD="...")
//   set LMS_LOOKUP_TOKEN_FILE=C:\path\lookup_token.txt     (optional)
//   php setup_lms_service.php <path-to-moodle-config.php> [--dry-run]

define('CLI_SCRIPT', true);
[$script, $configpath, $mode] = array_pad($argv, 3, null);
$dryrun = ($mode === '--dry-run');
if (!$configpath) {
    fwrite(STDERR, "usage: php setup_lms_service.php <moodle config.php> [--dry-run]\n");
    exit(2);
}
require($configpath);
require_once($CFG->libdir . '/accesslib.php');
require_once($CFG->dirroot . '/webservice/lib.php');
require_once($CFG->dirroot . '/mod/assign/locallib.php');

global $DB, $CFG;

function out($msg) { echo '[' . date('H:i:s') . "] $msg\n"; }
function fail($msg) { fwrite(STDERR, "ABORT: $msg\n"); exit(1); }

// ---------------------------------------------------------------- guards
$port = $CFG->dboptions['dbport'] ?? '';
if ($CFG->dbname !== 'moodle' || (string)$port !== '3307' || $CFG->wwwroot !== 'http://localhost:8081') {
    fail("unexpected Moodle target (db={$CFG->dbname}, port={$port}, wwwroot={$CFG->wwwroot})");
}
$password = getenv('LMS_STUDENT_TEST_PASSWORD');
if (!$password || strlen($password) < 10) {
    fail('set LMS_STUDENT_TEST_PASSWORD (at least 10 characters) before running');
}
$category = $DB->get_record('course_categories', ['idnumber' => 'FALL2026']);
if (!$category) {
    fail('synthetic category FALL2026 not found - is this the My Coach Moodle?');
}

const SERVICE_SHORTNAME = 'mycoach_lms';
const ROLE_SHORTNAME = 'mycoachlmsstudent';
const LOOKUP_SERVICE = 'mycoach_lms_lookup';
const LOOKUP_USERNAME = 'mycoach_lms_lookup';
const LOOKUP_ROLE = 'mycoachlmslookup';
const FUNCTIONS = [
    // identity / courses / content
    'core_webservice_get_site_info', 'core_user_get_users_by_field', 'core_enrol_get_users_courses',
    'core_course_get_courses_by_field', 'core_course_get_contents', 'core_course_view_course',
    // assignments
    'mod_assign_get_assignments', 'mod_assign_get_submission_status', 'mod_assign_save_submission',
    'mod_assign_submit_for_grading', 'mod_assign_view_submission_status',
    // quizzes
    'mod_quiz_get_quizzes_by_courses', 'mod_quiz_get_user_attempts', 'mod_quiz_get_user_best_grade',
    'mod_quiz_get_quiz_access_information', 'mod_quiz_get_attempt_access_information',
    'mod_quiz_get_quiz_required_qtypes', 'mod_quiz_start_attempt', 'mod_quiz_get_attempt_data',
    'mod_quiz_save_attempt', 'mod_quiz_process_attempt', 'mod_quiz_get_attempt_summary',
    'mod_quiz_get_attempt_review', 'mod_quiz_view_quiz', 'mod_quiz_view_attempt',
    'mod_quiz_view_attempt_summary', 'mod_quiz_view_attempt_review', 'mod_quiz_get_quiz_feedback_for_grade',
    // grades / completion
    'gradereport_user_get_grade_items', 'core_completion_get_activities_completion_status',
    'core_completion_get_course_completion_status', 'core_completion_update_activity_completion_status_manually',
    // calendar / notifications
    'core_calendar_get_action_events_by_timesort', 'core_calendar_get_calendar_events',
    'message_popup_get_popup_notifications', 'core_message_mark_notification_read',
    'core_message_get_unread_notification_count',
    // other learning resources
    'mod_resource_get_resources_by_courses', 'mod_resource_view_resource', 'mod_page_get_pages_by_courses',
    'mod_page_view_page', 'mod_url_view_url', 'mod_forum_get_forums_by_courses', 'mod_forum_get_forum_discussions',
];

\core\session\manager::set_user(get_admin());
$syscontext = context_system::instance();
$counts = array_fill_keys(['service_created', 'functions_added', 'role_created', 'role_assignments',
    'assignments_file_enabled', 'passwords_set', 'lookup_service_created', 'lookup_user_created'], 0);

$transaction = $DB->start_delegated_transaction();
try {
    // ------------------------------------------------------------ 1. external service
    $wsman = new webservice();
    $service = $DB->get_record('external_services', ['shortname' => SERVICE_SHORTNAME]);
    if (!$service) {
        $serviceid = $wsman->add_external_service((object)[
            'name' => 'My Coach LMS', 'shortname' => SERVICE_SHORTNAME, 'enabled' => 1,
            'restrictedusers' => 0, 'requiredcapability' => '', 'downloadfiles' => 1, 'uploadfiles' => 1,
        ]);
        $counts['service_created']++;
    } else {
        $serviceid = $service->id;
        if (!$service->enabled || !$service->uploadfiles || !$service->downloadfiles) {
            $DB->update_record('external_services', (object)['id' => $serviceid, 'enabled' => 1,
                'uploadfiles' => 1, 'downloadfiles' => 1]);
        }
    }
    foreach (FUNCTIONS as $fn) {
        if (!$DB->record_exists('external_functions', ['name' => $fn])) {
            out("skipping $fn (not available in this Moodle version)");
            continue;
        }
        if (!$wsman->service_function_exists($fn, $serviceid)) {
            $wsman->add_external_function_to_service($fn, $serviceid);
            $counts['functions_added']++;
        }
    }
    out("service " . SERVICE_SHORTNAME . " (id $serviceid): +{$counts['functions_added']} function(s)");

    // ------------------------------------------------------------ 2. role for synthetic students
    $roleid = $DB->get_field('role', 'id', ['shortname' => ROLE_SHORTNAME]);
    if (!$roleid) {
        $roleid = create_role('My Coach LMS student', ROLE_SHORTNAME,
            'Lets the synthetic My Coach students sign in to the My Coach LMS app (web service token + REST).', '');
        set_role_contextlevels($roleid, [CONTEXT_SYSTEM]);
        $counts['role_created']++;
    }
    assign_capability('moodle/webservice:createtoken', CAP_ALLOW, $roleid, $syscontext->id, true);
    assign_capability('webservice/rest:use', CAP_ALLOW, $roleid, $syscontext->id, true);

    $students = $DB->get_records_select('user',
        "deleted = 0 AND auth = 'manual' AND idnumber LIKE '6900__' AND username = " . $DB->sql_concat("'s'", 'idnumber'));
    foreach ($students as $u) {
        if (!preg_match('/^6900\d\d$/', $u->idnumber)) { continue; }
        if (!user_has_role_assignment($u->id, $roleid, $syscontext->id)) {
            role_assign($roleid, $u->id, $syscontext->id);
            $counts['role_assignments']++;
        }
        // ------------------------------------------------------------ 4. known test password
        update_internal_user_password($u, $password);
        unset_user_preference('auth_forcepasswordchange', $u);
        $counts['passwords_set']++;
    }
    out(count($students) . " synthetic student account(s) found");

    // ------------------------------------------------------------ 3. file submissions
    $courses = $DB->get_records('course', ['category' => $category->id]);
    foreach ($courses as $course) {
        foreach (get_coursemodules_in_course('assign', $course->id) as $cm) {
            $assign = new assign(context_module::instance($cm->id), $cm, $course);
            $plugin = $assign->get_submission_plugin_by_type('file');
            if ($plugin && !$plugin->is_enabled()) {
                $plugin->enable();
                $plugin->set_config('maxfilesubmissions', 3);
                $plugin->set_config('maxsubmissionsizebytes', 0);   // course / site limit
                $plugin->set_config('filetypeslist', '');
                $counts['assignments_file_enabled']++;
            }
        }
    }
    out("file submissions enabled on {$counts['assignments_file_enabled']} assignment(s)");

    // ------------------------------------------------------------ 5. sign-in lookup account
    // Students sign in with their student ID. Moodle's login/token.php needs the username, so the
    // LMS backend resolves "ID number -> username" with this separate, lookup-only account
    // (one function; it cannot read courses, grades or submissions). Its token is written to
    // LMS_LOOKUP_TOKEN_FILE (never printed).
    $lookupsvc = $DB->get_record('external_services', ['shortname' => LOOKUP_SERVICE]);
    if (!$lookupsvc) {
        $lookupsvcid = $wsman->add_external_service((object)[
            'name' => 'My Coach LMS sign-in lookup', 'shortname' => LOOKUP_SERVICE, 'enabled' => 1,
            'restrictedusers' => 1, 'requiredcapability' => '', 'downloadfiles' => 0, 'uploadfiles' => 0,
        ]);
        $counts['lookup_service_created']++;
    } else {
        $lookupsvcid = $lookupsvc->id;
    }
    if (!$wsman->service_function_exists('core_user_get_users_by_field', $lookupsvcid)) {
        $wsman->add_external_function_to_service('core_user_get_users_by_field', $lookupsvcid);
    }
    $lookupuser = $DB->get_record('user', ['username' => LOOKUP_USERNAME, 'deleted' => 0]);
    if (!$lookupuser) {
        require_once($CFG->dirroot . '/user/lib.php');
        $lookupuserid = user_create_user((object)['username' => LOOKUP_USERNAME, 'auth' => 'webservice',
            'firstname' => 'My Coach LMS', 'lastname' => 'sign-in lookup', 'email' => 'mycoach_lms_lookup@localhost.invalid',
            'emailstop' => 1, 'confirmed' => 1, 'mnethostid' => $CFG->mnet_localhost_id,
            'description' => 'Service account: resolves student ID -> username for the My Coach LMS sign-in.'], false, false);
        $lookupuser = $DB->get_record('user', ['id' => $lookupuserid], '*', MUST_EXIST);
        $counts['lookup_user_created']++;
    }
    if (!$DB->record_exists('external_services_users', ['externalserviceid' => $lookupsvcid, 'userid' => $lookupuser->id])) {
        $wsman->add_ws_authorised_user((object)['externalserviceid' => $lookupsvcid, 'userid' => $lookupuser->id]);
    }
    $lookuproleid = $DB->get_field('role', 'id', ['shortname' => LOOKUP_ROLE]);
    if (!$lookuproleid) {
        $lookuproleid = create_role('My Coach LMS sign-in lookup', LOOKUP_ROLE,
            'Lets the LMS sign-in lookup account read a user\'s username from their ID number.', '');
        set_role_contextlevels($lookuproleid, [CONTEXT_SYSTEM]);
    }
    foreach (['webservice/rest:use', 'moodle/user:viewdetails', 'moodle/user:viewalldetails', 'moodle/site:viewuseridentity'] as $cap) {
        assign_capability($cap, CAP_ALLOW, $lookuproleid, $syscontext->id, true);
    }
    if (!user_has_role_assignment($lookupuser->id, $lookuproleid, $syscontext->id)) {
        role_assign($lookuproleid, $lookupuser->id, $syscontext->id);
    }
    $tokenfile = getenv('LMS_LOOKUP_TOKEN_FILE');
    if ($tokenfile) {
        $existing = $DB->get_record_select('external_tokens', 'userid = ? AND externalserviceid = ? AND tokentype = ?',
            [$lookupuser->id, $lookupsvcid, EXTERNAL_TOKEN_PERMANENT], '*', IGNORE_MULTIPLE);
        $lookuptoken = $existing ? $existing->token
            : external_generate_token(EXTERNAL_TOKEN_PERMANENT, $lookupsvcid, $lookupuser->id, $syscontext);
        if (!$dryrun) { file_put_contents($tokenfile, $lookuptoken); }
        out('lookup token ' . ($existing ? 'reused' : 'created') . ' (written to LMS_LOOKUP_TOKEN_FILE)');
    }

    if ($dryrun) {
        out('DRY RUN, rolling back: ' . json_encode($counts));
        throw new moodle_exception('generalexceptionmessage', 'error', '', 'dry-run rollback (expected)');
    }
    $transaction->allow_commit();
} catch (Throwable $e) {
    try { $transaction->rollback($e); } catch (Throwable $rolledback) {
        if ($dryrun) { exit(0); }
        fwrite(STDERR, 'FAILED: ' . $rolledback->getMessage() . "\n");
        exit(1);
    }
}
accesslib_clear_all_caches(true);
purge_caches(['muc' => true, 'other' => false, 'theme' => false, 'lang' => false, 'js' => false, 'template' => false, 'filter' => false]);
out('COMMITTED: ' . json_encode($counts));
