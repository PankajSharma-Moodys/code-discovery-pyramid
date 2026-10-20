"""Every file inside a test module/project is role `test`, whatever its name."""

import unittest

from cdp.lang import classify_role, get_extractor


def role(path):
    return classify_role(path, get_extractor(path))


class TestModuleRole(unittest.TestCase):
    def test_files_in_test_modules_are_tests(self):
        for p in ("svc/Api.Tests/TestServerFactory.cs",
                  "svc/Api.Tests/Fakes/FakeDatabaseRepository.cs",
                  "svc/Api.Tests/Handlers/MoveTestsv2.cs",
                  "svc/Api.Integration.Tests/Api.Integration.Tests.csproj",
                  "svc/Core.UnitTests/SampleClass.cs",
                  "svc/Core.IntegrationTests/Util/Db.cs",
                  "svc/Core.Specs/Steps.cs",
                  "svc/Core.Test/Helper.cs",
                  "svc/Core.FunctionalTests/README.md",
                  "qe/workflow-qe-tests/src/main/java/Utils/Helper.java",
                  "qe/workflow-qe-tests/pom.xml",
                  "client/uds-client-it/src/main/java/A.java",
                  "pkg/testdata/sample.json",
                  "mod/src/integrationTest/java/A.java"):
            self.assertEqual(role(p), "test", p)

    def test_production_dirs_stay_source(self):
        for p in ("svc/Api/Handlers/Helper.cs",
                  "svc/latest/Foo.cs",
                  "svc/contest/Foo.cs",
                  "svc/Api.Contest/Foo.cs",       # `Contest`, not `Test`
                  "svc/Api.Latest/Foo.cs",
                  "src/main/scala/com.rms.execution.test/Foo.scala",
                  "src/main/java/TestUtils/Foo.java",
                  "svc/Api/TestServerFactory.cs",
                  "svc/Api/Tests.Core/Foo.cs".replace("Tests.Core", "Protest"),
                  "svc/it/Foo.java".replace("it/", "item/"),
                  "svc/audit/Foo.java"):
            self.assertEqual(role(p), "source", p)


if __name__ == "__main__":
    unittest.main()
