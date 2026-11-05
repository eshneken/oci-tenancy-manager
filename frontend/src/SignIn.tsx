import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import { Brand, defaultBranding } from "./Branding";
import type { BrandingView, SessionView } from "./contracts";

// Give all wrong factors/cooldowns the same guidance, without exposing credential/provider details.
function failureMessage(error: unknown) {
  return error instanceof ApiError && error.status === 401
    ? "Sign-in failed. Check your password and use a fresh authenticator code."
    : "Sign-in is temporarily unavailable. Please try again shortly.";
}

// Keep enrollment in the protected terminal; this form performs the real password/TOTP flow only.
export function SignIn({
  onSuccess,
  notice,
  branding = defaultBranding,
}: {
  onSuccess: (session: SessionView) => void | Promise<void>;
  notice: string;
  branding?: BrandingView;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>("");
  const submitting = useRef(false);
  // Keep factors out of the shared mutation cache and block same-tick duplicate submissions.
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
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
          <span className="eyebrow">RECOVERY ADMINISTRATOR</span>
          <h2>Sign in</h2>
          <p className="muted">
            Use your recovery password and authenticator code.
          </p>
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
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
            <button className="button primary full" disabled={pending}>
              {pending ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="corporate-note">Corporate sign-in is not configured.</p>
          <details className="setup-help">
            <summary>First-time local setup</summary>
            <p>Run the protected bootstrap command in your terminal:</p>
            <code>uv run --project backend otm-local bootstrap</code>
            <p>
              Enroll your authenticator there, then wait for a fresh code. Do
              not share your password or code in chat.
            </p>
          </details>
        </div>
      </section>
    </main>
  );
}
