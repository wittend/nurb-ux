import { useEffect, useRef, useState } from "react";
import { Channel, invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import Logo from "./Logo";
import { isLinux } from "./platform";
import { setupReportUrl } from "./setupReport";

type ProvisionEvent =
  | { kind: "stage"; stage: string }
  | { kind: "detail"; line: string };

// Stage ids arrive from provision.rs; the copy lives here. Hobbyist words
// only: no Python, no venv, no npm.
const STAGE_COPY: Record<string, string> = {
  python: "Getting things ready",
  deps: "Installing the CAD engine",
  warmup: "Preparing the CAD engine",
  chat: "Setting up the AI assistant",
};

/// First-launch provisioning screen. Mounts once, starts the install, and
/// hands the window back the moment the environment is healthy.
export default function Setup({ onDone, chatOnly = false }: { onDone: () => void; chatOnly?: boolean }) {
  const [stage, setStage] = useState<string | null>(null);
  const [line, setLine] = useState("");
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  const [offerChat, setOfferChat] = useState(false);
  const [installingChat, setInstallingChat] = useState(chatOnly);

  const start = async (installChat = chatOnly) => {
    setOfferChat(false);
    setInstallingChat(installChat);
    setError(null);
    const channel = new Channel<ProvisionEvent>();
    channel.onmessage = (event) => {
      if (event.kind === "stage") {
        setStage(event.stage);
        setLine("");
      } else {
        setLine(event.line);
      }
    };
    try {
      await invoke(installChat ? "provision_chat" : "provision", { onEvent: channel });
      if (!installChat && isLinux && !(await invoke<boolean>("provision_chat_status"))) setOfferChat(true);
      else onDone();
    } catch (e) {
      setError(String(e));
    }
  };

  // Opens a bug report with the error, app version, OS, and
  // architecture already filled in, so a failed setup never sends anyone
  // hunting through logs.
  const report = async () => {
    let version = "";
    try {
      const about = await invoke<{
        appVersion: string;
        nurbVersion: string;
        occtVersion: string | null;
        os: string;
        arch: string;
      }>("about_info");
      version = [
        `app ${about.appVersion}`,
        `CAD engine ${about.nurbVersion}`,
        about.occtVersion ? `OCCT ${about.occtVersion}` : null,
        `${about.os} (${about.arch})`,
      ]
        .filter(Boolean)
        .join("\n");
    } catch {
      // The report is still useful without version info.
    }
    openUrl(setupReportUrl(version, error ?? ""));
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={chatOnly ? "setup setup-overlay" : "setup"} data-tauri-drag-region>
      <div className="setup-card">
        <div className="setup-logo">
          <Logo size={40} />
        </div>
        <div className="setup-title">nurb</div>
        {offerChat ? (
          <>
            <div className="setup-stage">The CAD engine is ready</div>
            <div className="setup-note">AI tools are optional and require an internet download. Install them later in Settings.</div>
            <div className="setup-actions">
              <button className="setup-retry" onClick={() => start(true)}>download AI tools</button>
              <button className="setup-retry" onClick={onDone}>continue without AI</button>
            </div>
          </>
        ) : error ? (
          <>
            <div className="setup-error">{error}</div>
            <div className="setup-actions">
              <button className="setup-retry" onClick={() => start(installingChat)}>
                try again
              </button>
              <button className="setup-retry" onClick={report}>
                report this
              </button>
              {installingChat && <button className="setup-retry" onClick={onDone}>continue without AI</button>}
            </div>
          </>
        ) : (
          <>
            <div className="setup-stage">
              {(STAGE_COPY[stage ?? ""] ?? "Checking what's installed") + "…"}
            </div>
            <div className="setup-bar">
              <div className="setup-bar-fill" />
            </div>
            <div className="setup-detail">{line}</div>
            <div className="setup-note">
              Linux packages install the bundled CAD engine locally. Optional AI tools
              download separately. Your parts live in ordinary folders in Documents.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
