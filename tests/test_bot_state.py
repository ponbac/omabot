import json
from pathlib import Path
import runpy
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'bin/omabot-watch'
NOW = 1_800_000_000.0


def user(at):
    return {'kind': 'message', 'role': 'user', 'content': 'hi', 'timestampMs': at * 1000}


def bot(at, text='on it'):
    return {'kind': 'send-message', 'message': {'type': 'text', 'content': text}, 'timestampMs': at * 1000}


def card(at, prompt='Import both files?'):
    return {'kind': 'send-message', 'timestampMs': at * 1000,
            'message': {'type': 'widget', 'widget': {'prompt': prompt, 'options': []}}}


def event(at):
    return {'kind': 'event', 'event': {'type': 'automation-changed'}, 'timestampMs': at * 1000}


class BotStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.blob = Path(self.temp.name) / 'transcript.json'
        self.scope = runpy.run_path(str(HELPER))['working_state'].__globals__
        self.revision = 0

    def state(self, entries, now=NOW):
        self.revision += 1
        self.blob.write_text(json.dumps({'value': {'entries': entries}}))
        index = {'transcript.replicas.bot': (str(self.blob), self.revision)}
        return self.scope['working_state'](index, 'bot', now)

    def test_interim_acknowledgement_keeps_the_turn_working(self):
        working, since, _ = self.state([user(NOW - 30), bot(NOW - 28)])
        self.assertTrue(working)
        self.assertEqual(since, NOW - 30)

    def test_turn_ends_once_the_bot_goes_quiet(self):
        quiet = self.scope['WORK_QUIET_S']
        working, _, _ = self.state([user(NOW - quiet - 60), bot(NOW - quiet - 1)])
        self.assertFalse(working)

    def test_unanswered_message_works_until_the_cap(self):
        self.assertTrue(self.state([user(NOW - 60)])[0])
        self.assertFalse(self.state([user(NOW - self.scope['WORK_CAP_S'] - 1)])[0])

    def test_newest_card_is_waiting_on_you(self):
        _, _, prompt = self.state([user(NOW - 50), bot(NOW - 45), card(NOW - 40), event(NOW - 39)])
        self.assertEqual(prompt, 'Import both files?')

    def test_card_followed_by_anything_is_answered(self):
        self.assertEqual(self.state([card(NOW - 40), bot(NOW - 30)])[2], '')
        self.assertEqual(self.state([card(NOW - 40), user(NOW - 30)])[2], '')


if __name__ == '__main__':
    unittest.main()
