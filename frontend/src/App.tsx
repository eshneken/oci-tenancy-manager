import { ConfigurationDrift } from "./ConfigurationDrift";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Brand, useBranding } from "./Branding";
import { SignIn } from "./SignIn";
import { Administrators } from "./Administrators";
import { AuditHistory } from "./AuditHistory";
import { Tenancies } from "./Tenancies";
import { OrganizationMapping } from "./OrganizationMapping";
import { Organization } from "./Organization";
import { Operations } from "./Operations";
import { followLink, useNavigation } from "./navigation";
import { Baselines } from "./Baselines";
import { NavigationCount } from "./NavigationCount";
import { useActivity } from "./activity";

// One inventory keeps every private workflow cache behind the same sign-out/expiry boundary.
const privateQueries = [
  "email-policy",
  "configuration-drift",
  "configuration-check",
  "baselines",
  "administrators",
  "operations",
  "audit-history",
  "organization",
  "organization-mapping",
  "organization-reviews",
  "configuration-preview",
  "configuration-update",
  "person-workflow",
  "tenancies",
  "onboarding",
  "configuration-plan",
  "tenancy-override",
  "tenancy-deletion",
];

// Own verified-session navigation and clear administrator cache on logout or expiry.
export function App() {
  const client = useQueryClient();
  const branding = useBranding();
  const { path: currentPath, navigate, revision } = useNavigation();
  const path=currentPath.split(/[?#]/)[0];
  const page = useRef<HTMLElement>(null);
  const operationsPage =
    path === "/operations" || path.startsWith("/operations/");
  const tenancyPage = path === "/tenancies" || path.startsWith("/tenancies/");
  const organizationPage =
    path === "/organization" || path === "/organization/drift";
  const mappingPage = path.split("#")[0] === "/organization-mapping";
  const configurationPage = path.split("?")[0] === "/configuration";
  const driftPage = path === "/configuration/drift" || path.startsWith("/configuration/drift/");
  const auditPage = path === "/audit-history";
  const [notice, setNotice] = useState("");
  const session = useQuery({
    queryKey: ["session"],
    queryFn: ({ signal }) => api.session(signal),
    retry: false,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  });
  // Cancel before clearing so an older in-flight response cannot restore signed-out directory data.
  const signedOut = useCallback(
    async (message = "Your session ended. Sign in again.") => {
      await Promise.all([
        client.cancelQueries({ queryKey: ["session"] }),
        ...privateQueries.map((key) =>
          client.cancelQueries({ queryKey: [key] }),
        ),
      ]);
      privateQueries.forEach((key) =>
        client.removeQueries({ queryKey: [key] }),
      );
      client.setQueryData(["session"], null);
      setNotice(message);
      navigate("/login", true);
    },
    [client, navigate],
  );
  const expired = useCallback(() => void signedOut(), [signedOut]);
  // Delivery routing is private administrator context and cannot enable or change egress from the browser.
  const emailPolicy=useQuery({queryKey:["email-policy"],queryFn:({signal})=>api.emailPolicy(signal),enabled:Boolean(session.data),retry:false,refetchInterval:30_000,refetchOnWindowFocus:false});
  useEffect(()=>{if(session.data&&emailPolicy.error instanceof ApiError&&[401,403].includes(emailPolicy.error.status))expired();},[session.data,emailPolicy.error,expired]);
  const logout = useMutation({
    mutationFn: api.logout,
    retry: false,
    onSuccess: () => void signedOut("You have signed out."),
    onError: (error) => {
      // A 503 response clears the presented cookie; an unknown network result proves no logout.
      if (error instanceof ApiError && error.status === 503)
        void signedOut(
          "Browser credentials cleared, but server sign-out could not be confirmed.",
        );
      else setNotice("Sign-out could not be confirmed. Please try again.");
    },
  });
  useActivity(Boolean(session.data), expired);
  useEffect(() => {
    if (session.data === null) {
      privateQueries.forEach((key) =>
        client.removeQueries({ queryKey: [key] }),
      );
    }
  }, [session.data, client]);
  useEffect(() => {
    page.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [path, Boolean(session.data)]);
  // Canonical landing URLs open inventory; explicit feature URLs survive document reloads.
  useEffect(() => {
    if (session.data && (path === "/" || path === "/login")) navigate("/tenancies", true);
  }, [path, session.data, navigate]);
  if (session.isPending)
    return (
      <main className="session-status" role="status">
        Checking your session…
      </main>
    );
  if (session.isError)
    return (
      <main className="session-status">
        <h1>Unable to verify your session</h1>
        <p>Check that the local application and database are running.</p>
        <button
          className="button primary"
          onClick={() => void session.refetch()}
        >
          Try again
        </button>
      </main>
    );
  if (!session.data)
    return (
      <SignIn
        branding={branding}
        notice={notice}
        onSuccess={async (value) => {
          // An older unauthenticated poll cannot overwrite this newly verified session.
          await client.cancelQueries({ queryKey: ["session"] });
          client.setQueryData(["session"], value);
          setNotice("");
          navigate(path === "/" || path === "/login" ? "/tenancies" : currentPath, true);
        }}
      />
    );
  if (path === "/" || path === "/login")
    return <main className="session-status" role="status">Opening tenancies…</main>;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="/tenancies"
          className="brand"
          onClick={(event) => followLink(event, "/tenancies", navigate)}
        >
          <Brand branding={branding} />
        </a>
        <nav aria-label="Main navigation">
          <a
            href="/tenancies"
            className={"nav-item" + (tenancyPage ? " selected" : "")}
            aria-current={tenancyPage ? "page" : undefined}
            onClick={(event) => followLink(event, "/tenancies", navigate)}
          >
            Tenancies
          </a>
          <a
            href="/organization"
            className={
              "nav-item" + (path === "/organization" ? " selected" : "")
            }
            aria-current={path === "/organization" ? "page" : undefined}
            onClick={(event) => followLink(event, "/organization", navigate)}
          >
            Organization
          </a>
          <a
            href="/organization/drift"
            aria-label="Organization drift"
            aria-describedby="navigation-organization-count"
            className={
              "nav-item nav-child has-count" +
              (path === "/organization/drift" ? " selected" : "")
            }
            aria-current={path === "/organization/drift" ? "page" : undefined}
            onClick={(event) =>
              followLink(event, "/organization/drift", navigate)
            }
          >
            <span>Organization drift</span>
            <NavigationCount kind="organization" expired={expired} navigationRevision={revision} />
          </a>
          <a href="/configuration" className={"nav-item" + (configurationPage ? " selected" : "")} aria-current={configurationPage ? "page" : undefined} onClick={event => followLink(event, "/configuration", navigate)}>Configuration</a>
          <a href="/configuration/drift" className={"nav-item nav-child"+(driftPage?" selected":"")} aria-current={driftPage?"page":undefined} onClick={event=>followLink(event,"/configuration/drift",navigate)}>Configuration drift</a>
          <span className="nav-section">ACTIVITY &amp; HISTORY</span>
          <a
            href="/operations"
            aria-label="Operations"
            aria-describedby="navigation-operations-count"
            className={"nav-item has-count" + (operationsPage ? " selected" : "")}
            aria-current={operationsPage ? "page" : undefined}
            onClick={(event) => followLink(event, "/operations", navigate)}
          >
            <span>Operations</span>
            <NavigationCount kind="operations" expired={expired} navigationRevision={revision} />
          </a>
          <a
            href="/audit-history"
            className={"nav-item" + (auditPage ? " selected" : "")}
            aria-current={auditPage ? "page" : undefined}
            onClick={(event) => followLink(event, "/audit-history", navigate)}
          >
            Audit history
          </a>
          <span className="nav-section">APPLICATION SETTINGS</span>
          <a
            className={"nav-item" + (mappingPage ? " selected" : "")}
            href="/organization-mapping"
            aria-current={mappingPage ? "page" : undefined}
            onClick={(e) => followLink(e, "/organization-mapping", navigate)}
          >
            Organization Mapping
          </a>
          <a
            className={
              "nav-item" +
              (!operationsPage &&
              !auditPage &&
              !organizationPage &&
              !tenancyPage &&
              !mappingPage && !configurationPage && !driftPage
                ? " selected"
                : "")
            }
            href="/administrators"
            aria-current={
              !operationsPage &&
              !auditPage &&
              !organizationPage &&
              !tenancyPage &&
              !mappingPage && !configurationPage && !driftPage
                ? "page"
                : undefined
            }
            onClick={(event) => followLink(event, "/administrators", navigate)}
          >
            Administrators
          </a>
        </nav>
        <span className="environment">LOCAL ENVIRONMENT</span>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span className="workspace-id">{session.data.workspace_id}</span>
          <div className="account-menu">
            <span>{session.data.display_name}</span>
            <button
              className="button secondary"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              {logout.isPending ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <main className="page" ref={page}>
          {emailPolicy.data?.redirected&&<p className="notice email-routing-banner"><strong>Non-production email routing.</strong> New application email delivery goes to {emailPolicy.data.effective_test_email??"the configured test destination"}. Stored identities and previously recorded activation contacts remain unchanged.</p>}
          {notice && (
            <p role="alert" className="alert">
              {notice}
            </p>
          )}
          {driftPage ? <ConfigurationDrift key={path} identifier={path==="/configuration/drift"?null:path.slice("/configuration/drift/".length)} expired={expired} navigate={navigate}/> : configurationPage ? <Baselines expired={expired} navigate={navigate} /> : tenancyPage ? (
            <Tenancies
              identifier={
                path === "/tenancies" ? null : path.slice("/tenancies/".length)
              }
              expired={expired}
              navigate={navigate}
            />
          ) : organizationPage ? (
            <Organization
              drift={path === "/organization/drift"}
              expired={expired}
              navigate={navigate}
            />
          ) : mappingPage ? (
            <OrganizationMapping
              expired={expired}
              segmentId={currentPath.split("#segment-")[1]}
            />
          ) : auditPage ? (
            <AuditHistory expired={expired} navigate={navigate} />
          ) : operationsPage ? (
            <Operations
              operationId={
                path === "/operations"
                  ? null
                  : path.slice("/operations/".length)
              }
              expired={expired}
              navigate={navigate}
            />
          ) : (
            <Administrators expired={expired} />
          )}
        </main>
      </div>
    </div>
  );
}
