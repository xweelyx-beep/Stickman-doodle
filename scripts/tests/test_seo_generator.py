#!/usr/bin/env python3
"""Character-budget and formatting tests for the metadata generator.

    python3 scripts/tests/test_seo_generator.py

The point of this file is the arithmetic. A title that reads well and runs to
64 characters is truncated in Suggested Videos, and nothing downstream will say
so — the length rules only hold if something checks them on every shape the
generator can produce, not on one convenient example.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts", "core"))

import seo_generator as sg      # noqa: E402
import state_manager            # noqa: E402

# Deliberately varied: a short single word, a mid-length noun phrase, an
# operator acronym, a topic phrased as a question, and one long enough that no
# template can hold it inside the core band.
TOPICS = [
    ("anaesthesia", ["anaesthesia"]),
    ("why the brain clears waste during sleep", ["glymphatic system"]),
    ("how the international space station recycles water", ["ISS water recycling"]),
    ("why you keep eating sugar even when you are full", ["sugar cravings"]),
    ("what happens to a shipping container lost at sea in a winter storm",
     ["lost shipping containers", "container ship cargo loss"]),
]

BEATS = [{"name": "The problem"}, {"name": "The mechanism"},
         {"name": "Why it persists"}, {"name": "What to do"}, {"name": "Close"}]


def payloads(**kwargs):
    for topic, keywords in TOPICS:
        yield topic, sg.generate(topic, keywords, channel="stickman", **kwargs)


class TitleLengthTests(unittest.TestCase):
    def test_three_variants_in_order(self):
        for topic, payload in payloads():
            self.assertEqual([t["variant"] for t in payload["titles"]],
                             list(sg.VARIANTS), topic)

    def test_no_title_exceeds_the_hard_maximum(self):
        for topic, payload in payloads(beats=BEATS):
            for t in payload["titles"]:
                self.assertLessEqual(len(t["text"]), sg.TITLE_HARD_MAX,
                                     "%s: %s" % (topic, t["text"]))
                self.assertEqual(t["chars"], len(t["text"]))
                self.assertFalse(t["over_hard_max"])

    def test_titles_land_in_the_core_band(self):
        """40-50 characters is the target, and every topic in TOPICS reaches it.
        A topic that could not would still be emitted, flagged, and reported by
        validate() as a warning rather than silently truncated."""
        for topic, payload in payloads(beats=BEATS):
            for t in payload["titles"]:
                self.assertTrue(t["in_core_band"],
                                "%s: %s is %d chars" % (topic, t["text"], t["chars"]))
                self.assertGreaterEqual(t["chars"], sg.TITLE_CORE_MIN)
                self.assertLessEqual(t["chars"], sg.TITLE_CORE_MAX)

    def test_band_flags_are_consistent_with_the_string(self):
        for _, payload in payloads(beats=BEATS):
            for t in payload["titles"]:
                n = len(t["text"])
                self.assertEqual(t["in_core_band"],
                                 sg.TITLE_CORE_MIN <= n <= sg.TITLE_CORE_MAX)
                self.assertEqual(t["over_hard_max"], n > sg.TITLE_HARD_MAX)
                self.assertEqual(t["over_field_max"], n > sg.TITLE_FIELD_MAX)

    def test_alternates_are_distinct_and_within_the_field_limit(self):
        for _, payload in payloads(beats=BEATS):
            for t in payload["titles"]:
                self.assertNotIn(t["text"], t["alternates"])
                self.assertEqual(len(set(t["alternates"])), len(t["alternates"]))
                for alt in t["alternates"]:
                    self.assertLessEqual(len(alt), sg.TITLE_FIELD_MAX)

    def test_a_long_subject_is_flagged_not_silently_truncated(self):
        """A subject no template can hold inside 60 characters is reported, not
        cut. Trimming it would drop words the operator wrote and hand back a
        title that reads as if it had been chosen."""
        long_topic = ("the complete history of transatlantic undersea "
                      "telegraph cable repair operations")
        payload = sg.generate(long_topic, [long_topic], channel="stickman")
        self.assertFalse(payload["valid"])
        codes = [i["code"] for i in payload["validation"]]
        self.assertIn("titles.hard_max", codes)
        for t in payload["titles"]:
            self.assertTrue(t["over_hard_max"])
            self.assertFalse(t["in_core_band"])
            # every word of the subject survives; nothing was quietly dropped
            for word in long_topic.split():
                self.assertIn(word.lower(), t["text"].lower())


class TitleNumberTests(unittest.TestCase):
    """The number-driven variant is the one place a figure could be invented."""

    def test_no_number_without_a_count(self):
        payload = sg.generate("why the brain clears waste during sleep",
                              ["glymphatic system"], channel="stickman")
        curiosity = payload["titles"][0]
        self.assertIsNone(curiosity["number"])
        self.assertIsNone(curiosity["number_source"])
        self.assertNotRegex(curiosity["text"], r"\d")

    def test_the_number_comes_from_the_beat_count(self):
        payload = sg.generate("why the brain clears waste during sleep",
                              ["glymphatic system"], channel="stickman",
                              beats=BEATS)
        curiosity = payload["titles"][0]
        self.assertEqual(curiosity["number"], len(BEATS))
        self.assertEqual(curiosity["number_source"], "script beat count")
        self.assertIn(str(len(BEATS)), curiosity["text"])

    def test_a_recorded_number_always_carries_a_source(self):
        for _, payload in payloads(beats=BEATS):
            for t in payload["titles"]:
                if t["number"]:
                    self.assertTrue(t["number_source"])


class DescriptionTests(unittest.TestCase):
    def setUp(self):
        self.payload = sg.generate("why the brain clears waste during sleep",
                                   ["glymphatic system"], channel="stickman",
                                   beats=BEATS)
        self.desc = self.payload["description"]

    def test_block_order_is_hook_summary_queries(self):
        self.assertEqual([b["name"] for b in self.desc["blocks"]],
                         ["hook", "summary", "queries"])

    def test_hook_is_at_most_two_lines_and_carries_the_primary_keyword(self):
        self.assertLessEqual(len(self.desc["hook_lines"]), sg.HOOK_LINES)
        joined = " ".join(self.desc["hook_lines"]).lower()
        self.assertIn(self.payload["primary_keyword"], joined)

    def test_the_hook_opens_the_description(self):
        first_two = self.desc["text"].split("\n")[:len(self.desc["hook_lines"])]
        self.assertEqual(first_two, self.desc["hook_lines"])

    def test_summary_is_two_or_three_sentences(self):
        for _, payload in payloads(beats=BEATS):
            sentences = payload["description"]["summary_sentences"]
            self.assertGreaterEqual(len(sentences), sg.SUMMARY_SENTENCES_MIN)
            self.assertLessEqual(len(sentences), sg.SUMMARY_SENTENCES_MAX)
            for sentence in sentences:
                self.assertTrue(sentence.endswith("."), sentence)

    def test_summary_holds_without_beats(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman")
        self.assertGreaterEqual(len(payload["description"]["summary_sentences"]),
                                sg.SUMMARY_SENTENCES_MIN)

    def test_queries_block_header_and_bullet_count(self):
        for _, payload in payloads(beats=BEATS):
            desc = payload["description"]
            self.assertIn(sg.QUERIES_HEADER, desc["text"])
            self.assertGreaterEqual(len(desc["queries"]), sg.QUERIES_MIN)
            self.assertLessEqual(len(desc["queries"]), sg.QUERIES_MAX)
            bullets = [l for l in desc["text"].split("\n") if l.startswith("- ")]
            self.assertEqual(len(bullets), len(desc["queries"]))
            for query, bullet in zip(desc["queries"], bullets):
                self.assertEqual(bullet, "- %s" % query)

    def test_queries_are_unique_and_lowercase(self):
        queries = self.desc["queries"]
        self.assertEqual(len(set(queries)), len(queries))
        for q in queries:
            self.assertEqual(q, q.lower())

    def test_blocks_are_separated_by_a_blank_line(self):
        self.assertEqual(self.desc["text"].count("\n\n"),
                         len(self.desc["blocks"]) - 1)
        self.assertEqual(self.desc["chars"], len(self.desc["text"]))

    def test_chapters_are_appended_only_when_supplied(self):
        chapters = [{"timestamp": "00:00", "label": "Open"},
                    {"timestamp": "01:30", "label": "The mechanism"}]
        with_ch = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman",
                              chapters=chapters)
        self.assertIn("chapters", [b["name"] for b in with_ch["description"]["blocks"]])
        self.assertIn("01:30 The mechanism", with_ch["description"]["text"])
        self.assertNotIn("chapters", [b["name"] for b in self.desc["blocks"]])

    def test_no_search_volume_is_claimed(self):
        self.assertFalse(self.desc["volume_measured"])
        self.assertIn("no search-volume data was measured", self.desc["ranking_basis"])


class TagTests(unittest.TestCase):
    def test_count_is_within_the_band(self):
        for topic, payload in payloads(beats=BEATS):
            tags = payload["tags"]
            self.assertGreaterEqual(tags["count"], sg.TAGS_MIN, topic)
            self.assertLessEqual(tags["count"], sg.TAGS_MAX, topic)
            self.assertEqual(tags["count"], len(tags["tags"]))

    def test_every_tag_is_clean(self):
        for topic, payload in payloads(beats=BEATS):
            for tag in payload["tags"]["tags"]:
                self.assertEqual(tag, tag.lower(), topic)
                self.assertEqual(tag, tag.strip())
                self.assertNotIn("  ", tag)
                self.assertLessEqual(len(tag), sg.TAG_CHARS_MAX, tag)
                self.assertRegex(tag, r"^[a-z0-9' ]+$")

    def test_no_tag_repeats_a_word(self):
        """`how anaesthesia works works` is the spam shape this filter exists
        for — a frame applied to a keyword that already carries it."""
        for _, payload in payloads(beats=BEATS):
            for tag in payload["tags"]["tags"]:
                words = tag.split()
                self.assertEqual(len(set(words)), len(words), tag)

    def test_tags_are_unique(self):
        for _, payload in payloads(beats=BEATS):
            tags = payload["tags"]["tags"]
            self.assertEqual(len(set(tags)), len(tags))

    def test_the_channel_name_is_a_tag(self):
        for _, payload in payloads(beats=BEATS):
            tags = payload["tags"]
            self.assertTrue(tags["channel_tag_present"])
            self.assertIn("stickman", tags["tags"])

    def test_the_primary_keyword_is_a_tag(self):
        for _, payload in payloads(beats=BEATS):
            self.assertIn(payload["primary_keyword"], payload["tags"]["tags"])

    def test_the_field_string_fits_youtube(self):
        for _, payload in payloads(beats=BEATS):
            tags = payload["tags"]
            self.assertEqual(tags["field_string"], ",".join(tags["tags"]))
            self.assertEqual(tags["field_chars"], len(tags["field_string"]))
            self.assertLessEqual(tags["field_chars"], sg.TAGS_FIELD_MAX)

    def test_an_oversized_tag_is_rejected_with_a_reason(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman",
                              extra_tags=["a" * (sg.TAG_CHARS_MAX + 5)])
        reasons = [r["reason"] for r in payload["tags"]["rejected"]]
        self.assertTrue(any("characters" in r for r in reasons))
        for tag in payload["tags"]["tags"]:
            self.assertLessEqual(len(tag), sg.TAG_CHARS_MAX)


class ValidationTests(unittest.TestCase):
    def test_generated_payloads_validate(self):
        for topic, payload in payloads(beats=BEATS):
            errors = [i for i in payload["validation"] if i["severity"] == "error"]
            self.assertEqual(errors, [], topic)
            self.assertTrue(payload["valid"], topic)

    def test_validate_catches_a_long_title(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman")
        payload["titles"][0]["text"] = "x" * 70
        payload["titles"][0]["chars"] = 70
        payload["titles"][0]["over_hard_max"] = True
        codes = [i["code"] for i in sg.validate(payload)]
        self.assertIn("titles.hard_max", codes)

    def test_validate_catches_a_short_tag_list(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman")
        payload["tags"]["tags"] = payload["tags"]["tags"][:3]
        payload["tags"]["count"] = 3
        codes = [i["code"] for i in sg.validate(payload)]
        self.assertIn("tags.count", codes)

    def test_validate_catches_a_missing_queries_header(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman")
        payload["description"]["text"] = "no header here"
        codes = [i["code"] for i in sg.validate(payload)]
        self.assertIn("description.header", codes)

    def test_validate_catches_a_sourceless_number(self):
        payload = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman")
        payload["titles"][0]["number"] = 7
        payload["titles"][0]["number_source"] = None
        codes = [i["code"] for i in sg.validate(payload)]
        self.assertIn("titles.number_source", codes)


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_give_the_same_output(self):
        a = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman", beats=BEATS)
        b = sg.generate("anaesthesia", ["anaesthesia"], channel="stickman", beats=BEATS)
        for key in ("titles", "description", "tags", "title"):
            self.assertEqual(a[key], b[key])

    def test_operator_casing_survives_into_the_title(self):
        payload = sg.generate("how the international space station recycles water",
                              ["ISS water recycling"], channel="stickman")
        self.assertTrue(any("ISS" in t["text"] for t in payload["titles"]))
        self.assertIn("iss water recycling", payload["tags"]["tags"])


class StateAndExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="seo-generator-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def state_data(self, chosen_title=None):
        gate = {"payload": {"chosen_title": chosen_title} if chosen_title else {}}
        return {
            "episode_id": "20260902-anaesthesia",
            "channel": "stickman",
            "topic": "anaesthesia",
            "keywords": ["anaesthesia"],
            "seo": {"chapters": {"chapters": [
                {"timestamp": "00:00", "label": "Open"},
                {"timestamp": "02:00", "label": "The mechanism"}]}},
            "script": {"beats": BEATS},
            "gates": {state_manager.GATES["1"]["key"]: gate},
        }

    def test_from_state_uses_the_gate_1_title(self):
        payload = sg.from_state(self.state_data("Anaesthesia, Explained"))
        self.assertEqual(payload["title"], "Anaesthesia, Explained")
        self.assertEqual(payload["title_chars"], len("Anaesthesia, Explained"))
        self.assertEqual(payload["title_source"], "gate 1 selection")

    def test_from_state_says_when_no_title_was_selected(self):
        payload = sg.from_state(self.state_data())
        self.assertIn("gate 1 has not selected", payload["title_source"])
        self.assertEqual(payload["title"], payload["titles"][0]["text"])

    def test_from_state_carries_the_beats_and_chapters(self):
        payload = sg.from_state(self.state_data("Anaesthesia, Explained"))
        self.assertEqual(payload["titles"][0]["number"], len(BEATS))
        self.assertIn("02:00 The mechanism", payload["description"]["text"])

    def test_export_writes_readable_json(self):
        payload = sg.from_state(self.state_data("Anaesthesia, Explained"))
        path = sg.export(payload, os.path.join(self.tmp, "metadata.json"))
        with open(path, encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written["title"], "Anaesthesia, Explained")
        self.assertEqual(written["schema"], sg.SCHEMA)
        self.assertEqual(written["tags"]["field_string"],
                         payload["tags"]["field_string"])

    def test_the_episode_file_map_carries_metadata_json(self):
        self.assertEqual(state_manager.EPISODE_FILES["metadata_json"], "metadata.json")


class CliTests(unittest.TestCase):
    def test_cli_exits_zero_and_prints_the_tag_field(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sg.main(["--topic", "why the brain clears waste during sleep",
                            "--keyword", "glymphatic system",
                            "--channel", "stickman"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("glymphatic system", out)
        self.assertIn("tags:", out)

    def test_cli_json_round_trips(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sg.main(["--topic", "anaesthesia", "--keyword", "anaesthesia",
                     "--channel", "stickman", "--json"])
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["primary_keyword"], "anaesthesia")
        self.assertTrue(payload["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
