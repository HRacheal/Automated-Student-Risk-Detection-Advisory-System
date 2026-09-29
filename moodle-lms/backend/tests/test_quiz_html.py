"""Question HTML -> structured data, and the answer payload sent back to Moodle."""
from lms.quiz_html import FINISH_ONLY, build_submission, html_to_text, parse_question

# Shape of Moodle 4.1 true/false question HTML (question/type/truefalse/renderer.php)
TF_HTML = """
<div id="question-405-1" class="que truefalse deferredfeedback notyetanswered">
 <div class="info"><h3 class="no">Question <span class="qno">1</span></h3><div class="state">Not yet answered</div>
  <div class="grade">Marked out of 1.00</div>
  <div class="questionflag"><input type="hidden" name="q405:1_:flagged" value="0" /></div></div>
 <div class="content"><div class="formulation clearfix">
  <h4 class="accesshide">Question text</h4>
  <input type="hidden" name="q405:1_:sequencecheck" value="1" />
  <div class="qtext"><p>Synthetic statement 1 about DSA3010. True or false?</p></div>
  <fieldset class="ablock"><legend class="prompt h6 font-weight-normal sr-only">Question 1 Answer</legend>
   <div class="answer">
    <div class="r0"><input type="radio" name="q405:1_answer" value="1" id="q405:1_answertrue" /><label for="q405:1_answertrue" class="ml-1">True</label></div>
    <div class="r1"><input type="radio" name="q405:1_answer" value="0" id="q405:1_answerfalse" checked="checked" /><label for="q405:1_answerfalse" class="ml-1">False</label></div>
   </div></fieldset>
 </div></div>
</div>
"""

MULTI_HTML = """
<div class="que multichoice"><div class="formulation">
 <input type="hidden" name="q9:2_:sequencecheck" value="3" />
 <div class="qtext">Pick <b>all</b> primes</div>
 <input type="hidden" name="q9:2_choice0" value="0" />
 <input type="checkbox" name="q9:2_choice0" value="1" id="c0" aria-labelledby="c0_label" />
 <div id="c0_label"><span class="answernumber">a. </span>2</div>
 <input type="hidden" name="q9:2_choice1" value="0" />
 <input type="checkbox" name="q9:2_choice1" value="1" id="c1" checked="checked" aria-labelledby="c1_label" />
 <div id="c1_label"><span class="answernumber">b. </span>4</div>
 <script>alert('x')</script>
</div></div>
"""


def test_truefalse_parsed_into_plain_structured_data():
    q = parse_question({"slot": 1, "page": 0, "type": "truefalse", "html": TF_HTML, "status": "Not yet answered",
                        "stateclass": "notyetanswered", "maxmark": 1})
    assert q["text"] == "Synthetic statement 1 about DSA3010. True or false?"
    assert q["hidden"] == {"q405:1_:sequencecheck": "1"}          # flag field ignored
    [radio] = q["fields"]
    assert radio["kind"] == "radio" and radio["name"] == "q405:1_answer"
    assert radio["options"] == [{"value": "1", "label": "True"}, {"value": "0", "label": "False"}]
    assert radio["value"] == "0"                                    # the saved answer is pre-selected
    assert q["supported"] and not q["readonly"]


def test_checkbox_labels_and_no_markup_leaks():
    q = parse_question({"slot": 2, "html": MULTI_HTML})
    labels = [f["label"] for f in q["fields"]]
    assert labels == ["a. 2", "b. 4"]
    assert q["fields"][1]["checked"] is True
    assert "<" not in q["text"] and "alert" not in q["text"]


def test_submission_only_contains_fields_moodle_rendered():
    q = parse_question({"slot": 1, "html": TF_HTML})
    data = build_submission([q], {"q405:1_answer": "1", "q405:2_answer": "1", "q999:1_answer": "0",
                                  "q405:1_:sequencecheck": "99"})
    as_dict = {d["name"]: d["value"] for d in data}
    assert as_dict == {"q405:1_:sequencecheck": "1", "q405:1_answer": "1", "slots": "1"}


def test_unchecked_checkbox_sends_hidden_zero():
    q = parse_question({"slot": 2, "html": MULTI_HTML})
    as_dict = {d["name"]: d["value"] for d in build_submission([q], {"q9:2_choice0": "1"})}
    assert as_dict["q9:2_choice0"] == "1" and as_dict["q9:2_choice1"] == "0"


def test_finish_only_processes_no_question():
    assert FINISH_ONLY == [{"name": "slots", "value": ""}]


def test_html_to_text():
    assert html_to_text("<p>Line one</p><p>Line&nbsp;two</p>") == "Line one\nLine two"
    assert html_to_text(None) == ""
