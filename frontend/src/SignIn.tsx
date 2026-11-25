import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import { Brand, defaultBranding } from "./Branding";
import type { BrandingView, SessionView } from "./contracts";

// Give all wrong factors/cooldowns the same guidance, without exposing credential/provider details.
function failureMessage(error: unknown) {
  return error instanceof ApiError && error.status === 401
    ? "Sign-in failed. Check your password and use a fresh authenticator code."
    : "Sign-in is temporarily unavailable. Please try again shortly.";
}

// Lead with configured Oracle SSO and keep password/TOTP independently available for recovery.
export function SignIn({
  onSuccess,
  notice,
  branding = defaultBranding,
  corporateEnabled = false,
  corporateFailed = false,
}: {
  onSuccess: (session: SessionView) => void | Promise<void>;
  notice: string;
  branding?: BrandingView;
  corporateEnabled?: boolean;
  corporateFailed?: boolean;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>("");
  const submitting = useRef(false);
  const starting = useRef<AbortController | null>(null);
  const [corporatePending, setCorporatePending] = useState(false);
  const [corporateError, setCorporateError] = useState(corporateFailed);

  // Navigation or recovery can end the corporate attempt before it can redirect the browser.
  useEffect(() => () => starting.current?.abort(), []);

  // Only a successful same-origin start may navigate to a secure provider URL.
  async function startCorporate() {
    if (starting.current) return;
    const controller = new AbortController();
    starting.current = controller;
    setCorporatePending(true);
    setCorporateError(false);
    try {
      const { authorization_url } = await api.startCorporateSignIn(controller.signal);
      if (controller.signal.aborted) return;
      const provider = new URL(authorization_url);
      if (provider.protocol !== "https:" || provider.username || provider.password) {
        throw new Error("Invalid corporate sign-in URL");
      }
      window.location.assign(provider.href);
    } catch {
      if (controller.signal.aborted) return;
      setCorporateError(true);
      setCorporatePending(false);
      starting.current = null;
    }
  }

  // Keep factors out of the shared mutation cache and block same-tick duplicate submissions.
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    if (starting.current) {
      starting.current.abort();
      starting.current = null;
      setCorporatePending(false);
    }
    submitting.current = true;
    setPending(true);
    setError("");
    try {
      const session = await api.signIn(password, code);
      setPassword("");
      await onSuccess(session);
    } catch (failure) {
      setError(failureMessage(failure));
    } finally {
      setCode("");
      submitting.current = false;
      setPending(false);
    }
  }
  const recoveryForm = (
    <>
      <p className="muted">
        Use your recovery password and authenticator code.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={submit}>
        <label htmlFor="username">Username</label>
        <input
          id="username"
          value="recovery-admin"
          readOnly
          autoComplete="username"
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <label htmlFor="code">Authenticator code</label>
        <input
          id="code"
          autoComplete="one-time-code"
          inputMode="numeric"
          pattern="[0-9]{6}"
          required
          maxLength={6}
          aria-describedby="code-help"
          value={code}
          onChange={(event) =>
            setCode(event.target.value.replace(/\s/g, ""))
          }
        />
        <p id="code-help" className="field-help">
          Enter a fresh 6-digit code. Each code can be used once.
        </p>
        <button
        className={`button ${corporateEnabled ? "secondary" : "primary"} full`}
        disabled={pending}
      >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <details className="setup-help">
        <summary>First-time local setup</summary>
        <p>Run the protected bootstrap command in your terminal:</p>
        <code>uv run --project backend otm-local bootstrap</code>
        <p>
          Enroll your authenticator there, then wait for a fresh code. Do
          not share your password or code in chat.
        </p>
      </details>
    </>
  );
  return (
    <main className="signin-layout">
      <section className="signin-brand">
        <a href="/" className="brand">
          <Brand branding={branding} />
        </a>
        <div>
          <span className="eyebrow">ADMINISTRATION</span>
          <h1>
            One place for
            <br />
            tenancy oversight.
          </h1>
          <p>
            Accountability, access, and lifecycle management for your OCI
            organization.
          </p>
        </div>
        <span className="environment">LOCAL ENVIRONMENT</span>
      </section>
      <section className="signin-panel">
        <div className="signin-form">
          <span className="eyebrow">
            {corporateEnabled ? "Corporate SSO" : "Recovery administrator"}
          </span>
          <h2>Sign in</h2>
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
          {corporateEnabled ? (
            <>
              {corporateError && (
                <p className="alert" role="alert">
                  Oracle SSO could not complete. Please try again.
                </p>
              )}
              <button
                className="button primary full"
                disabled={corporatePending || pending}
                onClick={() => void startCorporate()}
              >
                {corporatePending ? "Opening Corporate SSO…" : "Sign in with Corporate SSO"}
              </button>
              <details className="setup-help recovery-sign-in">
                <summary>Recovery administrator sign-in</summary>
                {recoveryForm}
              </details>
            </>
          ) : recoveryForm}
        </div>
      </section>
    </main>
  );
}
