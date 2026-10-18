import datetime as dt
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import follow_loop_plan as flp  # noqa: E402

TODAY = dt.date(2026, 2, 5)


def acc(h, **kw):
    return {"handle": h, "last_post_days": 1, "verdict": "keep", "confidence": "high", "contribution": 0, **kw}


class Unfollow(unittest.TestCase):
    def plan(self, following, actions=()):
        return [x["handle"] for x in flp.build({}, following, [], list(actions), TODAY)["unfollow"]]

    def test_rules(self):
        self.assertEqual(self.plan([acc("old", last_post_days=90), acc("off", verdict="offtopic"),
                                    acc("unsure", verdict="offtopic", confidence="medium"),
                                    acc("twice", verdict="spam", confidence="medium", prev_verdict="spam"),
                                    acc("relay_ok", verdict="relay", contribution=2), acc("relay", verdict="relay"),
                                    acc("noisy", noise_days=3), acc("fine")]),
                         ["old", "off", "twice", "relay", "noisy"])

    def test_protected_never(self):
        self.assertEqual(self.plan([acc("boss", last_post_days=999, protected=True)]), [])

    def test_probation_window(self):
        f = lambda days, src="proven": {"at": (TODAY - dt.timedelta(days=days)).isoformat(), "handle": "n",
                                        "action": "follow", "ok": True, "source": src}
        self.assertEqual(self.plan([acc("n")], [f(35)]), ["n"])
        self.assertEqual(self.plan([acc("n")], [f(10)]), [])
        self.assertEqual(self.plan([acc("n")], [f(35, "official")]), [])
        self.assertEqual(self.plan([acc("n", contribution=1)], [f(35)]), [])


class Follow(unittest.TestCase):
    def test_priority_dedup_caps(self):
        cands = [{"handle": "q", "source": "quoted"}, {"handle": "o", "source": "official"},
                 {"handle": "p", "source": "project"}, {"handle": "have", "source": "project"},
                 {"handle": "o", "source": "proven"}, {"handle": "x", "source": "unknown"}]
        plan = flp.build({"following_cap": 10}, [acc("have")], cands, [], TODAY)
        self.assertEqual([x["handle"] for x in plan["follow"]], ["p", "o", "q"])
        plan = flp.build({"following_cap": 2}, [acc("have")], cands, [], TODAY)
        self.assertEqual([x["handle"] for x in plan["follow"]], ["p"])
        used = [{"at": TODAY.isoformat(), "handle": "z", "action": "follow", "ok": True}] * 4
        plan = flp.build({"following_cap": 10}, [acc("have")], cands, used, TODAY)
        self.assertEqual([x["handle"] for x in plan["follow"]], ["p"])


class Cli(unittest.TestCase):
    def test_samples_json_is_clean(self):
        s = ROOT / "samples/loop"
        out = subprocess.run([sys.executable, str(ROOT / "scripts/follow_loop_plan.py"), "--config", str(s / "config.sample.json"),
                              "--following", str(s / "following.sample.json"), "--candidates", str(s / "candidates.sample.json"),
                              "--actions", str(s / "actions.sample.jsonl"), "--today", "2026-02-05"],
                             capture_output=True, text=True, check=True).stdout
        plan = json.loads(out)
        self.assertEqual(len(plan["unfollow"]), 4)
        self.assertEqual(plan["follow"][0]["handle"], "project_offic")


if __name__ == "__main__":
    unittest.main()
