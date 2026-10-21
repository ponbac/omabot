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


def card(at, prompt='Import both files?', answer=None):
    entry = {'kind': 'send-message', 'timestampMs': at * 1000,
             'message': {'type': 'widget', 'widget': {'prompt': prompt, 'options': []}}}
    if answer is not None:
        entry['respondedValue'] = answer
    return entry


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

    def test_unanswered_message_is_working(self):
        working, since, _ = self.state([bot(NOW - 120), user(NOW - 5)])
        self.assertTrue(working)
        self.assertEqual(since, NOW - 5)

    def test_any_reply_ends_the_certain_window(self):
        # 0.71 cannot tell an interim "on it" from a final answer on disk, so
        # omabot does not guess: a done bot must never read as thinking.
        self.assertFalse(self.state([user(NOW - 30), bot(NOW - 28)])[0])

    def test_unanswered_message_works_until_the_cap(self):
        self.assertFalse(self.state([user(NOW - self.scope['WORK_CAP_S'] - 1)])[0])

    def test_open_card_is_waiting_on_you(self):
        _, _, prompt = self.state([user(NOW - 50), bot(NOW - 45), card(NOW - 40), event(NOW - 39)])
        self.assertEqual(prompt, 'Import both files?')

    def test_tapped_card_is_answered(self):
        self.assertEqual(self.state([card(NOW - 40, answer='Yes')])[2], '')
        self.assertEqual(self.state([card(NOW - 40, answer='Yes'), bot(NOW - 30)])[2], '')

    def test_card_answered_by_typing_is_answered(self):
        self.assertEqual(self.state([card(NOW - 40), user(NOW - 30)])[2], '')

    def test_skipped_card_is_resolved_without_reviving_older_prompt(self):
        skipped = dict(card(NOW - 30, prompt='Newest question'), widgetSkipped=True)
        working, _, prompt = self.state([
            card(NOW - 40, prompt='Older question'), skipped,
            event(NOW - 29), bot(NOW - 28),
        ])
        self.assertEqual(prompt, '')
        self.assertFalse(working)

    def test_only_true_skip_flag_resolves_an_unanswered_card(self):
        for value in (True, False, None, 0, 'true'):
            with self.subTest(widgetSkipped=value):
                entry = dict(card(NOW - 30), widgetSkipped=value)
                self.assertEqual(self.state([entry])[2], '' if value is True else 'Import both files?')

    def test_new_question_after_skipped_card_still_needs_answer(self):
        skipped = dict(card(NOW - 40, prompt='Skipped question'), widgetSkipped=True)
        self.assertEqual(self.state([skipped, card(NOW - 30, prompt='New question')])[2], 'New question')


if __name__ == '__main__':
    unittest.main()
