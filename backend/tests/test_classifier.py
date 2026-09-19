from app.classify.openai_classifier import apply_label_guards, _heuristic_label
from app.models import EmailLabel

BLOCKSTREAM = """Hi Thomas,

Thank you so much for your interest in joining Blockstream! We have received several applications for the Software Engineer, Enterprise Custody role and are doing our best to review them as quickly as possible.

If your qualifications meet our needs, one of our team members will get in touch with you in the coming weeks to schedule an interview.

Thank you again for your interest in our company. We really appreciate the time you invested in this application.

All the best,
Blockstream Hiring Team
"""

RULES_IQ = """Hi ,

Job –                  Datacenter Technician

Location –:       Remote (Must be within 45 minutes of Switch location in Lithia Springs, Georgia)

Duration- :       Long term contract

Mode of Interview: MS Teams with possible 2nd round face-to-face interview in Lithia Springs, GA

Job Description:

Summary:

To assist in managing the efficiency and optimal performance of the Lithia Springs and remote data centers.

Preferred Skills and Knowledge:

Advanced knowledge of servers, network cabling, and data center hardware

Atul Singh
Sr. Technical It Recruiter | Rules IQ
"""

KATE = """Hi Thomas,

You are confirmed for your interview with me on Wednesday September 16, 1:00pm (GMT-04:00) Eastern Time (US & Canada). I'll call you at +16789120809.

If you have any questions or need to reschedule, don't hesitate to reach out. I'm looking forward to speaking with you!

Thanks,

Kate
"""

SAGENT = """Hi Thomas!

Thanks for taking the time to apply to our Software Development Engineer SR -Full Stack Java/React role. We’re thrilled that you’d like to join us here at Sagent.

Now that we have your application, we’ll be in touch in the short term if we’d like to schedule an interview. Unfortunately, the days are short and the applicants are many so we won’t have time to meet everyone. If we don’t feel we’re a great match, we will let you know right away.

Again, thanks for your interest in Sagent!

Regards,
Sagent Talent Team
"""


def test_blockstream_is_applied():
    assert _heuristic_label("", "Blockstream", BLOCKSTREAM, "") == EmailLabel.APPLIED.value
    assert (
        apply_label_guards(EmailLabel.INTERVIEW.value, subject="", sender="", body_text=BLOCKSTREAM, snippet="")
        == EmailLabel.APPLIED.value
    )


def test_sagent_is_applied():
    assert _heuristic_label("", "Sagent", SAGENT, "") == EmailLabel.APPLIED.value
    assert (
        apply_label_guards(EmailLabel.INTERVIEW.value, subject="", sender="", body_text=SAGENT, snippet="")
        == EmailLabel.APPLIED.value
    )


def test_rules_iq_jd_is_alert():
    assert _heuristic_label("Datacenter Technician", "Atul Singh", RULES_IQ, "") == EmailLabel.ALERT.value
    assert (
        apply_label_guards(EmailLabel.INTERVIEW.value, subject="", sender="", body_text=RULES_IQ, snippet="")
        == EmailLabel.ALERT.value
    )


def test_kate_confirmation_is_interview():
    assert _heuristic_label("", "Kate", KATE, "") == EmailLabel.INTERVIEW.value
    assert (
        apply_label_guards(EmailLabel.INTERVIEW.value, subject="", sender="", body_text=KATE, snippet="")
        == EmailLabel.INTERVIEW.value
    )


UPSTART = """Hi Thomas Lee,

Thank you for your interest in opportunities at Upstart and for taking the time to apply.

We recommend applying to a small number of roles that closely match your experience and interests. Please note that candidates may apply to up to three roles within a 60 day period. At this time, you have reached that limit, so we will not be able to move forward with your most recent application.

You are welcome to reapply after the 60 day window has passed, and we encourage you to consider roles that closely align with your background.

We appreciate your interest in Upstart and wish you the best in your job search.

Best regards,
Upstart Recruiting Team
"""


def test_upstart_application_limit_is_rejected():
    assert _heuristic_label("", "Upstart", UPSTART, "") == EmailLabel.REJECTED.value
    assert (
        apply_label_guards(EmailLabel.OTHERS.value, subject="", sender="", body_text=UPSTART, snippet="")
        == EmailLabel.REJECTED.value
    )


STACKADAPT = """Hi Thomas,

Thank you for taking the time to apply for the Senior Quality Engineer position at StackAdapt. After carefully reviewing your application, we regret to inform you that we will not be moving forward with your application at this time.

Due to the high volume of applications we received, we are unable to provide individual feedback. However, we greatly appreciate your interest in our company and recognize the effort you put into your application.

We encourage you to keep an eye on our careers site for future opportunities that may be a great fit for you.

Best,

Talent Acquisition Team

StackAdapt
"""


def test_stackadapt_not_moving_forward_is_rejected():
    assert _heuristic_label("", "StackAdapt", STACKADAPT, "") == EmailLabel.REJECTED.value
    assert (
        apply_label_guards(EmailLabel.APPLIED.value, subject="", sender="", body_text=STACKADAPT, snippet="")
        == EmailLabel.REJECTED.value
    )
