import { compile } from "json-schema-to-typescript";
import { readFile, writeFile } from "node:fs/promises";
const names = [
  "fleet-refresh-request", "fleet-refresh-receipt", "fleet-refresh-status-request", "fleet-refresh-status",
 "signing-key-view", "signing-key-request",
 "recovery-password-view", "recovery-password-request", "recovery-password-disclosure",
 "recovery-network-preview", "recovery-network-request",
 "required-users-directory", "presence-check-request",
 "cost-refresh-request", "cost-refresh-receipt", "cost-view",
 "email-policy-view", "email-contacts", "email-route", "notification-summary",
 "responsibility-command",
 "configuration-repair-request", "configuration-drift-directory", "configuration-drift-query", "configuration-check-detail", "configuration-check-request",
 "override-editor", "override-preview-request", "configuration-plan", "configuration-plan-create", "configuration-plan-review",
  "configuration-preview", "configuration-update", "configuration-progress",
  "baseline-directory", "baseline-draft", "baseline-save", "baseline-version", "baseline-query", "baseline-publish",
  "mapping-settings", "mapping-request", "mapping-apply", "mapping-preview",
  "tenancy-deletion-command", "tenancy-deletion-preview",
  "onboarding-command", "onboarding-view",
  "organization-action", "organization-action-receipt", "organization-person-workflow",
  "organization-review-directory", "organization-review-query", "tenancy-directory", "tenancy-detail", "tenancy-query",
  "organization-directory",
  "organization-query",
  "organization-outcome",
  "branding-view",
  "administrator-directory",
  "administrator-query",
  "session-view",
  "operation-directory",
  "operation-detail",
  "operation-query",
  "operation-acceptance",
  "inspection-submission",
  "sandbox-catalog",
  "audit-directory",
  "audit-query",
  "audit-export-query",
];
const properties = {},
  definitions = {};
for (const name of names) {
  const schema = JSON.parse(
    await readFile(
      new URL("../backend/contracts/" + name + ".schema.json", import.meta.url),
      "utf8",
    ),
  );
  Object.assign(definitions, schema.$defs ?? {});
  delete schema.$defs;
  properties[schema.title] = schema;
}
const schema = {
  title: "ApiContracts",
  type: "object",
  properties,
  required: Object.keys(properties),
  $defs: definitions,
  additionalProperties: false,
};
const content =
  "// Generated from authoritative Pydantic schemas.\n" +
  (await compile(schema, "ApiContracts", {
    bannerComment: "",
    additionalProperties: false,
    style: { printWidth: 80 },
  }));
const path = new URL("./src/contracts.ts", import.meta.url);
if (process.argv.includes("--check")) {
  if ((await readFile(path, "utf8")) !== content)
    throw new Error("Frontend contracts are stale");
} else await writeFile(path, content);
