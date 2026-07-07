import resend
resend.api_key = "re_2s99KBSr_CCCFW6zP5bgYF21YpgQ5j2Lm"
r = resend.Emails.send({
    "from": "Master Events <noreply@masterevents.events>",
    "to": ["judeosamong@gmail.com"],
    "subject": "Test from Master Events",
    "html": "<h1>Test email</h1><p>If you see this, Resend is working!</p>",
    "text": "Test email - Resend is working!",
})
print(r)
