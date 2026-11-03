# haranogiyeche
Community-based Lost &amp; Found platform with verified ownership claims.

## Selenium browser tests

Install the browser-test dependency with `python -m pip install -r requirements-e2e.txt`,
then run `python manage.py test e2e_tests.test_selenium`. The test uses headless
Chrome; Selenium Manager will locate or download the matching Chrome driver. It
exercises the public pages, registration/login, community creation and joining,
posts, verification questions, claims, moderation, notifications, messaging, and
profile.
