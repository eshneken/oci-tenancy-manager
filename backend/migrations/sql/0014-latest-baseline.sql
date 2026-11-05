-- Latest publication now governs new admissions; retain historical metadata and accepted pins.
-- Invalidate previews that may have displayed the withdrawn selectable default.
UPDATE public.org_workspace SET registry_revision=registry_revision+1;
