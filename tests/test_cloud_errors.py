"""What the admin reads when restic / rclone fail (samples of their real output)."""
from datetime import datetime

from app import cloud

MISSING = """Fatal: unable to open config file: <config/> does not exist
Is there a repository at the following location?
rclone:karta-store:Karta-backups"""
LOCKED = """unable to create lock in backend: repository is already locked by PID 1343 on karta by app (UID 10001, GID 10001)
lock was created at 2026-10-05 23:40:02 (1h2m3.4s ago)
storage ID 21a3d67c
the `unlock` command can be used to remove stale locks"""
WRONG_PASSWORD = "Fatal: wrong password or no key found"
EXPIRED = """rclone: 2026/10/05 23:40:05 ERROR : : couldn't list files: couldn't fetch token: invalid_grant: maybe token expired? - try refreshing with "rclone config reconnect karta-store:"
Fatal: unable to open repository at rclone:karta-store:Karta-backups: error talking HTTP to rclone: exit status 1"""
FORBIDDEN = "Fatal: unable to save snapshot: googleapi: Error 403: The user's Drive storage quota has been exceeded., storageQuotaExceeded"
OTHER = """Fatal: unable to save snapshot: rclone: response status 500
  unexpected EOF
connection reset by peer"""


def test_known_errors_become_clear_greek_messages():
    assert cloud.explain(MISSING) == "Δεν βρέθηκαν αντίγραφα σε αυτόν τον φάκελο του cloud"
    assert cloud.explain(LOCKED) == "Τα αντίγραφα είναι κλειδωμένα από προηγούμενη εργασία που διακόπηκε"
    assert cloud.explain(WRONG_PASSWORD) == "λάθος κωδικός κρυπτογράφησης"
    assert cloud.explain(EXPIRED) == "Η πρόσβαση στο cloud έληξε — συνδέστε ξανά"
    assert cloud.explain(FORBIDDEN) == "Ο χώρος στο cloud γέμισε"
    assert cloud.explain("Error 401: Request had invalid authentication credentials.") == \
        "Η πρόσβαση στο cloud έληξε — συνδέστε ξανά"


def test_anything_else_keeps_its_last_lines():
    assert cloud.explain(OTHER) == ("Fatal: unable to save snapshot: rclone: response status 500 · unexpected EOF · "
                                    "connection reset by peer")
    assert len(cloud.explain("x" * 1000)) == 300
    assert cloud.explain("", "rclone", 3) == "rclone: κωδικός 3"
    assert cloud.explain("lock was created by PID 4031") .startswith("lock")     # a number is not an HTTP status


def test_a_new_repository_over_old_backups_is_still_recognised():
    assert "already exists" in cloud.explain("Fatal: create repository at rclone:karta-store:Karta-backups failed: "
                                             "config file already exists")


def test_a_slow_cloud_is_explained():
    raw = ('Fatal: unable to open repository at rclone:karta-store:Karta-backups: error talking HTTP to rclone: '
           'Get "http://localhost/file-11248313741212961703": context deadline exceeded '
           '(Client.Timeout exceeded while awaiting headers)')
    assert cloud.explain(raw).startswith("Το cloud άργησε να απαντήσει")


def test_snapshot_times_are_shown_in_athens_time():
    """restic writes the machine's local time with its offset; it was read as UTC and shown 3 hours late."""
    assert cloud.snapshot_time("2026-10-07T13:32:10.123456789+03:00") == datetime(2026, 10, 7, 13, 32, 10)
    assert cloud.snapshot_time("2026-10-07T10:32:10.5Z") == datetime(2026, 10, 7, 13, 32, 10)     # summer: UTC+3
    assert cloud.snapshot_time("2026-12-07T10:32:10Z") == datetime(2026, 12, 7, 12, 32, 10)       # winter: UTC+2
    assert cloud.snapshot_time("2026-10-07T13:32:10+0300") == datetime(2026, 10, 7, 13, 32, 10)
    assert cloud.snapshot_time("garbage") is None
