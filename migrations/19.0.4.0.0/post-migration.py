# -*- coding: utf-8 -*-
"""19.0.4.0.0 — Auto-apply shipped excise rates on every upgrade.

Wires the new ``apply_shipped_excise_data`` helper from hooks.py
into the upgrade flow so non-technical contributors can keep
the module's tax rates in sync with Skatteverket without writing
SQL or one-off migrations every time:

  1. Update SHIPPED_EXCISE_TAX_TYPES in hooks.py with the new rate.
  2. Update the matching value in data/excise_tax_data.xml (so
     fresh installs land on the same value too).
  3. Bump the manifest version.
  4. Copy this migration file into a new
     migrations/<new-version>/ folder. The file is short — the
     boilerplate just calls apply_shipped_excise_data(env).

Existing databases that run -u then automatically write the new
rate to their excise.tax.type rows. The data file is noupdate=1
so accountant-side customisations (name, posting account, tags)
survive; only the engine-critical fields listed in the
SHIPPED_EXCISE_TAX_TYPES dict get refreshed.

If a future round only changes hooks.py (no data-file change),
this migration still runs and applies the new value — that's the
whole point.
"""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.l10n_se_excise_tax.hooks import (
        apply_shipped_excise_data,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_shipped_excise_data(env)
