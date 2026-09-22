import { useState } from "react";
import { useControlRoomStore } from "../../store/controlRoomStore.ts";

/** Paste-once control for the `X-CDP-Web-Token` `uvicorn` prints to stdout
 * at startup (`web/api/auth.py`) -- there is no cookie/session, so the
 * browser has no other way to learn it. Persisted in `localStorage` via the
 * store; shown collapsed once a token is set. */
export function TokenGate() {
  const authToken = useControlRoomStore((s) => s.authToken);
  const setAuthToken = useControlRoomStore((s) => s.setAuthToken);
  const [draft, setDraft] = useState("");

  if (authToken) {
    return (
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--atlas-text-dim)" }}>
        <span>mutation token set</span>
        <button onClick={() => setAuthToken(null)} className="underline" style={{ color: "var(--atlas-text-dim)" }}>
          clear
        </button>
      </div>
    );
  }

  return (
    <form
      className="flex items-center gap-2 text-xs"
      onSubmit={(e) => {
        e.preventDefault();
        if (draft.trim()) setAuthToken(draft.trim());
      }}
    >
      <input
        type="password"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="X-CDP-Web-Token (from uvicorn stdout)"
        className="w-64 rounded border px-2 py-1"
        style={{ background: "var(--atlas-bg-2)", borderColor: "var(--atlas-border)", color: "var(--atlas-text)" }}
      />
      <button
        type="submit"
        className="atlas-btn-primary rounded px-2 py-1"
        style={{ background: "var(--atlas-accent)", color: "#07090c" }}
      >
        save
      </button>
    </form>
  );
}
