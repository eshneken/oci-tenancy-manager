/** Shared current-design navigation; page bodies retain their separately approved authority. */
(() => {
  'use strict';
  const manifest = Object.freeze([
    {id: 'tenancies', label: 'Tenancies', href: 'financial-walkthrough.html#tenancies'},
    {id: 'organization', label: 'Organization', children: [
      {id: 'organization-drift', label: 'Organization drift'}
    ]},
    {id: 'configuration', label: 'Configuration', href: 'configuration-walkthrough.html#configurations', children: [
      {id: 'baselines', label: 'Baselines', href: 'configuration-walkthrough.html#configurations'},
      {id: 'configuration-drift', label: 'Configuration drift', href: 'configuration-walkthrough.html#drift'}
    ]},
    {id: 'activity-history', label: 'Activity & history', section: true},
    {id: 'operations', label: 'Operations', href: 'operations-walkthrough.html#queued'},
    {id: 'audit-history', label: 'Audit History'},
    {id: 'application-settings', label: 'Application settings', section: true},
    {id: 'administrators', label: 'Administrators'}
  ]);

  // Link only to an existing static destination; missing page bodies remain inert context labels.
  function menuItem(item, current) {
    const node = document.createElement(item.href ? 'a' : 'span');
    node.textContent = item.label;
    node.className = 'design-nav-item' + (item.href ? '' : ' design-nav-context');
    node.dataset.navigationItem = item.id;
    // Same-document hashes preserve query and tab-local published/review state during navigation.
    if (item.href) {
      const destination = new URL(item.href, location.href);
      node.href = destination.pathname === location.pathname ? destination.hash : item.href;
    }
    if (item.id === current) {
      node.classList.add('is-current');
      node.setAttribute('aria-current', item.href ? 'page' : 'location');
    }
    return node;
  }

  // Render daily work, activity/history and application settings without treating history as an inbox.
  function render(target, current) {
    const nav = typeof target === 'string' ? document.getElementById(target) : target;
    if (!nav) return;
    nav.className = 'design-navigation';
    nav.setAttribute('aria-label', 'Design walkthrough navigation');
    const list = document.createElement('ul');
    list.className = 'design-nav-list';
    for (const item of manifest) {
      const row = document.createElement('li');
      if (item.section) {
        row.className = 'design-nav-section';
        const title = document.createElement('p');
        title.textContent = item.label;
        row.append(title);
      } else {
        row.className = 'design-nav-group';
        const label = menuItem(item, current);
        if (item.children?.some(child => child.id === current)) {
          label.classList.add('is-parent-current');
        }
        row.append(label);
        if (item.children) {
          const children = document.createElement('ul');
          children.className = 'design-nav-children';
          for (const child of item.children) {
            const childRow = document.createElement('li');
            childRow.append(menuItem(child, current));
            children.append(childRow);
          }
          row.append(children);
        }
      }
      list.append(row);
    }
    nav.replaceChildren(list);
  }
  window.DesignNavigation = Object.freeze({manifest, render});
})();
