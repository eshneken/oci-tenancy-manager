// Keep manual obligations discoverable without confusing identity removal with resource cleanup.
export function CleanupResponsibilities() {
  return <details className="operator-instructions">
    <summary>Manual cleanup responsibilities</summary>
    <div className="operator-instructions-body">
      <p>Coordinate this work with the current tenancy owner. For user-removal steps, OTM removes only the recorded personal user and its group memberships.</p>
      <ul>
        <li>Review resources the departing member owned or managed, in their assigned compartment and any shared compartments. Preserve or transfer anything still needed, then clean up only the resources approved for removal. Preserve other members’ resources and shared or system services.</li>
        <li>If a dedicated compartment was created for this person, verify it is empty before deleting it manually. Do not delete an existing shared compartment or anything still used by other members.</li>
        <li>Review additional users, API keys and other credentials they created. Manually remove or transfer those that are no longer needed; preserve shared, service, automation and recovery accounts.</li>
        <li>If the resource scope is unknown, identify it with the tenancy owner. User removal does not discover or delete these resources, compartments or additional accounts, and does not verify completion of this manual cleanup.</li>
      </ul>
    </div>
  </details>;
}
