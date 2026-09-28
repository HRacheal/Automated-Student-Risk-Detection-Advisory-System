<?php
// Populates Moodle with the SYNTHETIC My Coach dataset using Moodle-native APIs
// (the same data generator Moodle's own "Make test course" admin tool uses, plus
// the assign / quiz attempt APIs). Only historical timestamps and last-access
// values - which no Moodle API can set - are written directly.
//
// Usage (run with Moodle's own PHP):
//   php moodle_populate_synthetic.php <path-to-moodle-config.php> <path-to-seed.json>
//
// Contains no credentials. Aborts before writing if the target is not the
// expected Moodle database or if any synthetic record already exists.

define('CLI_SCRIPT', true);
[$script, $configpath, $seedpath, $mode] = array_pad($argv, 4, null);
$rehearsal = ($mode === '--rehearsal');
if (!$configpath || !$seedpath) {
    fwrite(STDERR, "usage: php moodle_populate_synthetic.php <moodle config.php> <seed.json>\n");
    exit(2);
}
require($configpath);
require_once($CFG->libdir . '/clilib.php');
require_once($CFG->dirroot . '/lib/phpunit/classes/util.php');
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/mod/quiz/locallib.php');
require_once($CFG->dirroot . '/mod/quiz/attemptlib.php');
require_once($CFG->libdir . '/gradelib.php');
require_once($CFG->libdir . '/completionlib.php');
require_once($CFG->libdir . '/questionlib.php');

global $DB, $CFG, $USER;
$CFG->noemailever = true;   // runtime only: never send e-mail during population

function out($msg) { echo '[' . date('H:i:s') . "] $msg\n"; }
function fail($msg) { fwrite(STDERR, "ABORT: $msg\n"); exit(1); }
function ts($iso) {
    if ($iso === null) { return 0; }
    $iso = strlen($iso) === 10 ? $iso . 'T00:00' : $iso;
    return (new DateTime($iso, new DateTimeZone('Africa/Nairobi')))->getTimestamp();
}

// ---------------------------------------------------------------- guards
$port = $CFG->dboptions['dbport'] ?? '';
if ($CFG->dbname !== 'moodle' || (string)$port !== '3307' || $CFG->wwwroot !== 'http://localhost:8081') {
    fail("unexpected Moodle target (db={$CFG->dbname}, port={$port}, wwwroot={$CFG->wwwroot})");
}
$seed = json_decode(file_get_contents($seedpath), true);
if (empty($seed['meta']['synthetic'])) { fail('seed is not flagged synthetic'); }
$students = array_values(array_filter($seed['students'], fn($s) => !empty($s['moodle'])));
$codes = array_column($seed['sections'], 'code');
[$insql, $inparams] = $DB->get_in_or_equal($codes);
if ($DB->record_exists_select('course', "shortname $insql", $inparams)) { fail('a synthetic course shortname already exists'); }
if ($DB->record_exists_select('user', "username LIKE 's6900%' OR idnumber LIKE '6900%' OR username LIKE 'inst.%'")) {
    fail('synthetic users already exist');
}
if ($DB->record_exists('course_categories', ['idnumber' => 'FALL2026'])) { fail('category FALL2026 already exists'); }
foreach ($seed['students'] as $s) {
    if ((string)$s['student_id'] === '690013' && !empty($s['moodle'])) { fail('690013 must not have a Moodle account'); }
}

\core\session\manager::set_user(get_admin());
$gen = phpunit_util::get_data_generator();
$counts = array_fill_keys(['categories', 'courses', 'instructors', 'students', 'enrolments', 'questions', 'assignments',
    'quizzes', 'submissions', 'late_submissions', 'assignment_grades', 'quiz_attempts', 'course_access_rows'], 0);

$transaction = $DB->start_delegated_transaction();
try {
    // ------------------------------------------------------------ structure
    $cat = $gen->create_category(['name' => 'Fall 2026', 'idnumber' => 'FALL2026',
        'description' => 'Synthetic My Coach demonstration courses (fictitious data).']);
    $counts['categories']++;

    $users = [];
    foreach ($seed['instructors'] as $i) {
        $users[$i['username']] = $gen->create_user(['username' => $i['username'], 'firstname' => $i['firstname'],
            'lastname' => $i['lastname'], 'email' => $i['email'], 'emailstop' => 1, 'auth' => 'manual',
            'password' => random_string(24) . 'Aa1!', 'description' => 'Synthetic instructor account (My Coach demo).']);
        $counts['instructors']++;
    }
    foreach ($students as $s) {
        $m = $s['moodle'];
        $users[$m['username']] = $gen->create_user(['username' => $m['username'], 'idnumber' => $m['idnumber'],
            'firstname' => $m['firstname'], 'lastname' => $m['lastname'], 'email' => $m['email'], 'emailstop' => 1,
            'auth' => 'manual', 'password' => random_string(24) . 'Aa1!',
            'description' => 'Synthetic student account (My Coach demo). Not a real person.']);
        $counts['students']++;
    }
    out("users: {$counts['instructors']} instructors, {$counts['students']} students");

    $act = $seed['moodle_activities'];
    $courses = $assigns = $quizzes = $questions = [];
    foreach ($seed['sections'] as $sec) {
        $mc = $sec['moodle'];
        $course = $gen->create_course(['category' => $cat->id, 'shortname' => $mc['shortname'], 'fullname' => $mc['fullname'],
            'idnumber' => $mc['idnumber'], 'startdate' => ts($mc['startdate']), 'enddate' => ts($mc['enddate']),
            'enablecompletion' => 1, 'format' => 'topics', 'numsections' => 6,
            'summary' => 'Synthetic course for the My Coach demonstration (fictitious data).']);
        $courses[$sec['code']] = $course;
        $counts['courses']++;
        $gen->enrol_user($users[$sec['instructor']]->id, $course->id, 'editingteacher', 'manual', ts($mc['startdate']));

        // Native question bank API (the test-only question generator needs PHPUnit helpers)
        $qcat = question_make_default_categories([context_course::instance($course->id)]);
        foreach ($act['question_bank_per_course'] as $qdef) {
            $ready = \core_question\local\bank\question_version_status::QUESTION_STATUS_READY;
            $question = (object)['qtype' => 'truefalse', 'category' => $qcat->id, 'createdby' => get_admin()->id,
                'idnumber' => null, 'status' => $ready];
            $form = (object)['category' => $qcat->id . ',' . $qcat->contextid, 'name' => "{$sec['code']} Q{$qdef['n']}",
                'questiontext' => ['text' => "Synthetic statement {$qdef['n']} about {$sec['code']}. True or false?", 'format' => FORMAT_HTML],
                'generalfeedback' => ['text' => '', 'format' => FORMAT_HTML], 'defaultmark' => 1, 'penalty' => 1,
                'correctanswer' => $qdef['correct'] ? '1' : '0',
                'feedbacktrue' => ['text' => '', 'format' => FORMAT_HTML], 'feedbackfalse' => ['text' => '', 'format' => FORMAT_HTML],
                'status' => $ready];
            $q = question_bank::get_qtype('truefalse')->save_question($question, $form);
            $questions[$sec['code']][] = ['id' => $q->id, 'correct' => $qdef['correct'] ? 1 : 0];
            $counts['questions']++;
        }
        foreach ($act['assignments'] as $a) {
            // Created WITHOUT a cut-off so the assign API accepts the (backdated) submissions;
            // the seed cut-off date is applied once the submissions exist.
            $assigns[$sec['code']][$a['n']] = $gen->create_module('assign', ['course' => $course->id, 'section' => $a['n'],
                'name' => $a['name'], 'intro' => 'Synthetic weekly assignment.',
                'allowsubmissionsfromdate' => ts($a['allow_from']), 'duedate' => ts($a['due'] . 'T23:59'),
                'cutoffdate' => 0, 'gradingduedate' => ts($a['due']) + 7 * DAYSECS, 'grade' => $a['max_grade'],
                'assignsubmission_onlinetext_enabled' => 1, 'assignsubmission_file_enabled' => 0, 'submissiondrafts' => 0,
                'requiresubmissionstatement' => 0, 'sendnotifications' => 0, 'sendlatenotifications' => 0,
                'sendstudentnotifications' => 0, 'completion' => COMPLETION_TRACKING_AUTOMATIC, 'completionsubmit' => 1]);
            $counts['assignments']++;
        }
        foreach ($act['quizzes'] as $qz) {
            $quiz = $gen->create_module('quiz', ['course' => $course->id, 'section' => $qz['n'] * 2, 'name' => $qz['name'],
                'intro' => 'Synthetic quiz.', 'timeopen' => ts($qz['opens']), 'timeclose' => ts($qz['closes'] . 'T23:59'),
                'grade' => $qz['max_grade'], 'sumgrades' => 0, 'attempts' => 1, 'questionsperpage' => 0,
                'preferredbehaviour' => 'deferredfeedback', 'completion' => COMPLETION_TRACKING_AUTOMATIC, 'completionusegrade' => 1]);
            $quizrec = $DB->get_record('quiz', ['id' => $quiz->id], '*', MUST_EXIST);
            foreach ($questions[$sec['code']] as $slot => $qq) {
                quiz_add_quiz_question($qq['id'], $quizrec, 0, $qz['slot_marks'][$slot]);
            }
            quiz_update_sumgrades($DB->get_record('quiz', ['id' => $quiz->id]));
            $quizzes[$sec['code']][$qz['n']] = $DB->get_record('quiz', ['id' => $quiz->id]);
            $counts['quizzes']++;
        }
        out("course {$sec['code']}: 5 questions, 6 assignments, 3 quizzes");
    }

    // ------------------------------------------------------------ enrolments (active registrations only)
    foreach ($students as $s) {
        $regs = [];
        foreach ($s['rosario']['current_registrations'] as $r) {
            if ($r['end_date'] === null) { $regs[$r['code']] = $r['start_date']; }
        }
        foreach ($s['moodle']['courses'] as $c) {
            if (!isset($regs[$c['code']])) { throw new moodle_exception('generalexceptionmessage', 'error', '', "enrolment without active registration: {$s['student_id']} {$c['code']}"); }
            $gen->enrol_user($users[$s['moodle']['username']]->id, $courses[$c['code']]->id, 'student', 'manual', ts($regs[$c['code']]));
            $counts['enrolments']++;
        }
    }
    out("enrolments: {$counts['enrolments']}");

    // ------------------------------------------------------------ activity
    $studentgrade = function ($s, $ci, $n, $late) {
        $scores = [];
        foreach ($s['moodle']['courses'] as $c) {
            foreach ($c['quizzes'] as $q) { if ($q['score_percent'] !== null) { $scores[] = $q['score_percent']; } }
        }
        $base = $scores ? array_sum($scores) / count($scores) : 60;
        $g = (int) round($base + ((($s['student_id'] + $ci * 7 + $n * 3) % 11) - 5) - ($late ? 5 : 0));
        return max(0, min(100, $g));
    };
    $marks = $act['quizzes'][0]['slot_marks'];
    $total = array_sum($marks);
    foreach ($students as $s) {
        $u = $users[$s['moodle']['username']];
        foreach ($s['moodle']['courses'] as $ci => $c) {
            $course = $courses[$c['code']];
            foreach ($c['assignments'] as $a) {
                if (!in_array($a['status'], ['submitted', 'late'], true)) { continue; }
                $cm = get_coursemodule_from_instance('assign', $assigns[$c['code']][$a['n']]->id, $course->id, false, MUST_EXIST);
                $assign = new assign(context_module::instance($cm->id), $cm, $course);
                \core\session\manager::set_user($u);
                $data = (object)['userid' => $u->id, 'onlinetext_editor' => ['itemid' => file_get_unused_draft_itemid(),
                    'text' => "Synthetic submission by {$s['moodle']['username']} for {$c['code']} Assignment {$a['n']}.",
                    'format' => FORMAT_HTML]];
                $notices = [];
                if (!$assign->save_submission($data, $notices)) {
                    throw new moodle_exception('generalexceptionmessage', 'error', '', "submission failed {$u->username} {$c['code']} A{$a['n']}: " . implode('; ', $notices));
                }
                \core\session\manager::set_user(get_admin());
                $sub = $DB->get_record('assign_submission', ['assignment' => $assign->get_instance()->id, 'userid' => $u->id, 'latest' => 1], '*', MUST_EXIST);
                if ($sub->status !== 'submitted') { throw new moodle_exception('generalexceptionmessage', 'error', '', "status {$sub->status} for {$u->username}"); }
                $when = ts($a['submitted_at']);
                $DB->update_record('assign_submission', (object)['id' => $sub->id, 'timecreated' => $when, 'timemodified' => $when, 'timestarted' => $when]);
                $assign->save_grade($u->id, (object)['grade' => $studentgrade($s, $ci, $a['n'], $a['status'] === 'late'),
                    'attemptnumber' => 0, 'addattempt' => 0, 'workflowstate' => '', 'applytoall' => 0, 'sendstudentnotifications' => 0]);
                $DB->set_field('course_modules_completion', 'timemodified', $when, ['coursemoduleid' => $cm->id, 'userid' => $u->id]);
                $counts['submissions']++;
                $counts['assignment_grades']++;
                if ($a['status'] === 'late') { $counts['late_submissions']++; }
            }
            foreach ($c['quizzes'] as $q) {
                if ($q['status'] !== 'attempted') { continue; }
                $quizrec = $quizzes[$c['code']][$q['n']];
                $target = (int) round($q['score_percent'] / 100 * $total);
                $chosen = null;   // subset of slots answered correctly whose marks sum to the target
                for ($mask = 0; $mask < (1 << count($marks)) && $chosen === null; $mask++) {
                    $sum = 0;
                    foreach ($marks as $i => $mk) { if ($mask & (1 << $i)) { $sum += $mk; } }
                    if ($sum === $target) { $chosen = $mask; }
                }
                if ($chosen === null) { throw new moodle_exception('generalexceptionmessage', 'error', '', "no mark subset for {$q['score_percent']}%"); }
                $tstart = ts($q['attempted_at']);
                $tfinish = $tstart + 15 * MINSECS;
                \core\session\manager::set_user($u);
                $quizobj = quiz::create($quizrec->id, $u->id);
                $quba = question_engine::make_questions_usage_by_activity('mod_quiz', $quizobj->get_context());
                $quba->set_preferred_behaviour($quizobj->get_quiz()->preferredbehaviour);
                $attempt = quiz_create_attempt($quizobj, 1, null, $tstart, false, $u->id);
                quiz_start_new_attempt($quizobj, $quba, $attempt, 1, $tstart);
                quiz_attempt_save_started($quizobj, $quba, $attempt);
                $attemptobj = quiz_attempt::create($attempt->id);
                $responses = [];
                foreach ($questions[$c['code']] as $i => $qq) {
                    $right = (bool)($chosen & (1 << $i));
                    $responses[$i + 1] = ['answer' => $right ? $qq['correct'] : 1 - $qq['correct']];
                }
                $attemptobj->process_submitted_actions($tfinish, false, $responses);
                $attemptobj->process_finish($tfinish, false);
                \core\session\manager::set_user(get_admin());
                $cm = get_coursemodule_from_instance('quiz', $quizrec->id, $course->id, false, MUST_EXIST);
                $DB->set_field('course_modules_completion', 'timemodified', $tfinish, ['coursemoduleid' => $cm->id, 'userid' => $u->id]);
                $counts['quiz_attempts']++;
            }
            if ($c['last_course_access']) {
                $row = $DB->get_record('user_lastaccess', ['userid' => $u->id, 'courseid' => $course->id]);
                if ($row) {
                    $DB->set_field('user_lastaccess', 'timeaccess', ts($c['last_course_access']), ['id' => $row->id]);
                } else {
                    $DB->insert_record('user_lastaccess', (object)['userid' => $u->id, 'courseid' => $course->id,
                        'timeaccess' => ts($c['last_course_access'])]);
                }
                $counts['course_access_rows']++;
            }
        }
        // site-level access (no API can set historical values)
        $site = ts($s['moodle']['site_last_access']);
        $first = $site ? min($site, ts('2026-08-31T09:00')) : 0;
        $DB->update_record('user', (object)['id' => $u->id, 'firstaccess' => $first, 'lastaccess' => $site,
            'lastlogin' => $site, 'currentlogin' => $site]);
        out("student {$s['student_id']}: activity done");
    }

    // apply the seed's cut-off dates now that submissions exist
    foreach ($assigns as $code => $list) {
        foreach ($act['assignments'] as $a) {
            $DB->set_field('assign', 'cutoffdate', ts($a['cutoff'] . 'T23:59'), ['id' => $list[$a['n']]->id]);
        }
    }
    foreach ($courses as $course) { grade_regrade_final_grades($course->id); }
    if ($rehearsal) {
        out('REHEARSAL complete, rolling back everything: ' . json_encode($counts));
        throw new moodle_exception('generalexceptionmessage', 'error', '', 'rehearsal rollback (expected)');
    }
    $transaction->allow_commit();
} catch (Throwable $e) {
    $transaction->rollback($e);
}
rebuild_course_cache(0, true);
out('COMMITTED. created: ' . json_encode($counts));
