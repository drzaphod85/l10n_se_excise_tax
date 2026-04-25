# -*- coding: utf-8 -*-
"""19.0.2.0.0 — Phase 0 (Kemikalieskatt 2026 rate update) +
Phase 1 (excise.tax.type generalisation: unit_basis + country_id) +
Phase 2a (Nikotinskatt — three new taxes).

The data file is ``noupdate="1"`` so a plain ``-u`` does NOT
overwrite existing ``excise.tax.type`` records. This script applies
the per-row updates via SQL on already-installed databases.
Fresh installs from 19.0.2.0.0+ get the right values directly from
the data file.

Concretely:

1. **Rate update.** Skatteverket raised the chemical-tax rates on
   2026-01-01:
     - Electronics (High Rate): 114.00 → 180.71 SEK/kg
     - Major Appliances (Low Rate): 11.00 → 12.42 SEK/kg
     - Per-unit cap: 562.00 → 552.27 SEK/unit

2. **unit_basis default.** All shipped excise.tax.type rows are
   weight-based (kg). New installs get ``unit_basis='kg'`` from
   the data file; existing rows keep NULL until this script runs.

3. **country_id default.** Same shape — set to ``base.se`` on rows
   that don't already have a country set.

4. **Bind BAS accounts for the new Nikotinskatt taxes.** The data
   file creates the three new ``account.tax`` records on upgrade
   (noupdate=1 blocks UPDATEs to existing records, not the creation
   of new ones), but ``post_init_hook`` only runs at install. We
   re-invoke the binding logic from here so the new tax records
   get their liability account on existing databases too.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT res_id, name FROM ir_model_data
         WHERE module = 'l10n_se_excise_tax'
           AND model = 'excise.tax.type'
           AND name IN ('excise_type_electronics',
                        'excise_type_major_appliances')
        """
    )
    rows = dict(cr.fetchall())  # {res_id: xmlid}

    # Reverse mapping for the rate update.
    by_xmlid = {xmlid: res_id for res_id, xmlid in rows.items()}

    # 1. Rate update.
    rate_updates = {
        'excise_type_electronics':       (180.71, 552.27),
        'excise_type_major_appliances':  (12.42,  552.27),
    }
    for xmlid, (rate, cap) in rate_updates.items():
        if xmlid not in by_xmlid:
            continue
        cr.execute(
            """
            UPDATE excise_tax_type
               SET tax_rate = %s,
                   max_limit = %s
             WHERE id = %s
            """,
            (rate, cap, by_xmlid[xmlid]),
        )

    # 2. unit_basis default — only for rows that don't have one yet.
    #    Existing chemical-tax rows are kg-based; setting NULL → 'kg'
    #    keeps them computing correctly under the new dispatch.
    cr.execute(
        """
        UPDATE excise_tax_type
           SET unit_basis = 'kg'
         WHERE unit_basis IS NULL
        """
    )

    # 2b. has_reduction_levels — only the two shipped Kemikalieskatt
    #     types support the 50%/90% reduction scheme. Set the flag
    #     on those existing rows (the data file is noupdate=1 so
    #     a plain -u doesn't overwrite the field).
    if by_xmlid:
        cr.execute(
            """
            UPDATE excise_tax_type
               SET has_reduction_levels = TRUE
             WHERE id = ANY(%s)
            """,
            (list(by_xmlid.values()),),
        )
    # Default everything else to FALSE explicitly to be safe.
    cr.execute(
        """
        UPDATE excise_tax_type
           SET has_reduction_levels = FALSE
         WHERE has_reduction_levels IS NULL
        """
    )

    # 3. country_id default — point all currently-untagged rows at
    #    Sweden (base.se).
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'base' AND name = 'se'
        """
    )
    se_row = cr.fetchone()
    if se_row:
        cr.execute(
            """
            UPDATE excise_tax_type
               SET country_id = %s
             WHERE country_id IS NULL
            """,
            (se_row[0],),
        )

    # 4. Bind BAS accounts for the newly-created Nikotinskatt taxes.
    #    Re-invoke the post-init hook against the fresh repartition
    #    lines (it only acts on those with account_id=False, so the
    #    chemical-tax bindings made on the original install are not
    #    disturbed).
    from odoo import api, SUPERUSER_ID
    from odoo.addons.l10n_se_excise_tax.hooks import post_init_hook
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
