import type { EmailContacts as Contacts, EmailRoute } from "./contracts";

// Keep original identity contacts visible while showing the exact frozen external-delivery destination.
function Contact({label,route}:{label:string;route:EmailRoute}) {
  return <div><dt>{label}</dt><dd>{route.redirected ? <><span className="cell-secondary">Original contact: {route.original_email??"Not configured"}</span><span>Test delivery: {route.effective_email??"Not configured"}</span></> : route.effective_email??"Not configured"}</dd></div>;
}

// Legacy operations keep their original contact fields; a current global override cannot rewrite old intent.
export function EmailContactSummary({contacts,activation}:{contacts?:Contacts|null;activation:boolean}) {
  if(!contacts)return null;
  const redirected=contacts.owner.redirected||contacts.activation.redirected;
  return <section className="email-contact-summary full-field" aria-label="Tenancy email contacts"><h3>Tenancy email contacts</h3><dl className="email-contact-facts"><Contact label={activation?"Activation / bootstrap email":"Bootstrap contact email"} route={contacts.activation}/><Contact label="Owner invitation email" route={contacts.owner}/></dl>{redirected&&<p className="muted">Non-production delivery uses the test addresses shown. Stored administrator and employee identities remain unchanged.</p>}</section>;
}
