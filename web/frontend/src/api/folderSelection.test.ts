import { describe, expect, it } from "vitest";
import { currentRepoRow, repoIdForPath } from "./folderSelection.ts";

describe("repoIdForPath", () => {
  const repos = [{ repo_id: "demo", repo_path: "/a/demo" }, { repo_id: "x", repo_path: null }];
  it("uses the matching registry row's id", () => {
    expect(repoIdForPath("/a/demo", repos)).toBe("demo");
  });
  it("falls back to the path when unregistered", () => {
    expect(repoIdForPath("/b/new", repos)).toBe("/b/new");
  });
});

describe("currentRepoRow", () => {
  const rows = [{ repo_id: "served" }, { repo_id: "other" }];
  it("falls back to the first row when nothing was picked", () => {
    expect(currentRepoRow(rows, null)?.repo_id).toBe("served");
  });
  it("matches an explicit id", () => {
    expect(currentRepoRow(rows, "other")?.repo_id).toBe("other");
  });
  it("does not fall back for an unmatched explicit id", () => {
    expect(currentRepoRow(rows, "/new")).toBeUndefined();
  });
  it("is undefined for an empty list", () => {
    expect(currentRepoRow([], null)).toBeUndefined();
  });
});
