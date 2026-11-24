"""Replay the real Module 13 -> 14 -> 15 hand-off offline, retaining the same tables between lessons."""
import contextlib
import io
import unittest

import test_evaluation
import test_pipelines
import test_release


class FreshnessTests(unittest.TestCase):
    def test_new_batches_change_expected_facts_and_block_the_old_endpoint(self):
        pipeline = test_pipelines.PipelineTests()
        pipeline.setUp()
        self.addCleanup(pipeline.doCleanups)
        pipeline.run_lesson(create_pipeline=True, run_pipeline=True, run_job=True)
        evaluation = test_evaluation.NotebookTests()
        evaluation.setUp()
        self.addCleanup(evaluation.doCleanups)
        namespace = evaluation.run_lesson(source_spark=pipeline.spark, endpoint=True,
                                          run_evaluation=True, evaluate_endpoint=True)
        # Independently known from the shipped CSVs plus the three synthetic batches.
        self.assertEqual([t["fact"] for t in namespace["TASKS"][:2]], ["11", "22"])
        self.assertEqual(namespace["availability_key"], "seats_live")
        self.assertFalse(namespace["endpoint_verdict"]["passed"])
        self.assertTrue(namespace["refreshed_verdict"]["passed"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(pipeline.course.check("14.1"))

        release = test_release.NotebookTests()
        release.setUp()
        self.addCleanup(release.doCleanups)
        namespace = release.run_lesson(source_spark=pipeline.spark, log_candidates=True, release_candidate=True)
        self.assertEqual(namespace["availability_key"], "seats_live")
        self.assertEqual([t["fact"] for t in namespace["TASKS"][:2]], ["11", "22"])
        self.assertTrue(namespace["good_verdict"]["passed"])
        self.assertFalse(namespace["bad_verdict"]["passed"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(pipeline.course.check("15.1"))


if __name__ == "__main__":
    unittest.main()
