"""C# partial test classes (`FooTests.Part.cs`) classify as tests, like `FooTests.cs`."""

import unittest

from cdp.lang import classify_role, get_extractor


def role(path):
    return classify_role(path, get_extractor(path))


class PartialTestRole(unittest.TestCase):
    def test_partial_test_files_are_tests(self):
        for p in ("svc/Api.Core/Handlers/MoveHandlerTests.Cleanup.cs",
                  "svc/Api.Core/Handlers/MoveHandlerTests.Helpers.cs",
                  "svc/Api.Core/MoveHandlerTest.Validation.cs",
                  "svc/Api.Core/MoveHandlerTests.Error_Handling.Part2.cs",
                  "MoveHandlerTests.cs"):
            self.assertEqual(role(p), "test", p)

    def test_ordinary_multi_dot_sources_stay_source(self):
        for p in ("app/Forms/Foo.Designer.cs",
                  "app/Contest.cs",
                  "app/Contest.Rules.cs",
                  "app/Tests.Helpers.cs",       # no class name before `Tests`
                  "app/Tests.cs",
                  "app/TestsRunner.Part.cs",    # `Tests` is not the stem's end
                  "app/Foo.Tests.Extensions.cs",  # class `Foo`, not a test class
                  "app/Foo.g.cs"):
            self.assertEqual(role(p), "source", p)

    def test_rule_is_csharp_only(self):
        # Java/Kotlin/Scala keep their single-suffix rule; no part-segment form.
        self.assertEqual(role("src/main/java/a/FooTest.java"), "test")
        self.assertEqual(role("src/main/java/a/FooTest.Part.java"), "source")
        self.assertEqual(role("src/main/scala/a/FooSpec.Part.scala"), "source")


if __name__ == "__main__":
    unittest.main()
