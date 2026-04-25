# -*- coding: utf-8 -*-
"""19.0.3.0.0 — Phase 2b (Tobaksskatt: six new excise types and six
new account.tax records).

The data file is ``noupdate="1"`` so Odoo only creates records that
don't already exist on upgrade — the new tobacco rows get created
on existing databases automatically. What this migration does is
re-invoke ``post_init_hook`` so the freshly-created tobacco
repartition lines get bound to a BAS account (2630 → 2640 → 2980)
on companies that have a Swedish chart of accounts. The hook is
idempotent: it only touches repartition lines whose
``account_id=False``, so existing chemical-tax / nicotine-tax
bindings are not disturbed.
"""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.l10n_se_excise_tax.hooks import post_init_hook
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
