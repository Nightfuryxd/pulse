---
name: test-all-providers
description: Test every configured notification provider in PULSE
user_invocable: true
---

Test all PULSE notification providers:

1. First call `GET http://localhost:8001/api/notifications/providers` to see which are configured
2. For each provider that shows `configured: true` or has credentials set:
   - **webhook**: POST test to httpbin.org/post
   - **telegram**: POST test to chat ID 982892344
   - **slack**: POST test (will use configured token)
   - **email**: POST test (skip if SMTP not configured)
   - **sms**: POST test (skip if Twilio not configured)
   - **discord/teams/google_chat/zoom**: POST test (skip if no webhook URL)
   - **pagerduty/opsgenie**: POST test (skip if no API key)
   - **whatsapp/whatsapp_meta**: POST test (skip if not configured)

Use the endpoint: `POST http://localhost:8001/api/notifications/test`
Body: `{"provider": "<name>", "target": "<target>", "message": "PULSE Provider Test"}`

3. Report results table: Provider | Status | Details
