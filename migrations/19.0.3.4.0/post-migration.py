# -*- coding: utf-8 -*-
"""19.0.3.4.0 — Re-assert engine-critical settings on the shipped
``excise.tax.type`` records.

Why this exists: the data file (``data/excise_tax_data.xml``) ships
with ``noupdate="1"`` so accountant-side customisations (renamed
labels, adjusted rates, custom posting accounts) survive module
upgrades. The trade-off is that field changes on the *shipped*
records — the things the module's engine actually relies on, like
``has_reduction_levels`` on Kemikalieskatt — are not re-applied on
``-u``.

If a database somehow ends up with a stale value on those flags
(an interrupted migration in the past, an older version that
predates the field, a copy of an older db…) the engine breaks
silently:
- ``has_reduction_levels = FALSE`` on Kemikalieskatt → the
  Reduction Level field disappears from the product form, and the
  engine ignores any reduction set on existing products.
- ``unit_basis IS NULL`` → engine returns 0 excise per line.
- ``country_id IS NULL`` → fold and exemption checks may fail.

Rather than relying on the once-and-only-once 19.0.2.0.0 migration
to set these values, this module ships an idempotent post-migration
that runs at *every* upgrade and re-asserts the engine-critical
fields on the Kemikalieskatt rows specifically. Only the technical
flags are forced; user-editable fields (name, rate, max_limit) are
left alone — accountants can adjust those without us overwriting.

Pattern to follow when adding a new excise category in the future:
either include its xmlid in ``KEMIKALIESKATT_TYPES`` here OR add
its own re-assert block. Tobacco / nicotine don't need it — they
ship with ``has_reduction_levels = FALSE`` (the default), and the
engine does the right thing whether the field is FALSE or NULL.
"""


# Excise Type xmlids that belong to Kemikalieskatt (have the
# 50%/90% reduction selector on the product form).
KEMIKALIESKATT_TYPE_XMLIDS = (
    'excise_type_electronics',
    'excise_type_major_appliances',
)


def migrate(cr, version):
    # Resolve xmlids to record ids.
    cr.execute(
        """
        SELECT name, res_id
          FROM ir_model_data
         WHERE module = 'l10n_se_excise_tax'
           AND model = 'excise.tax.type'
           AND name = ANY(%s)
        """,
        (list(KEMIKALIESKATT_TYPE_XMLIDS),),
    )
    kemikalieskatt_ids = [row[1] for row in cr.fetchall()]
    if not kemikalieskatt_ids:
        # Module installed but the types aren't in this DB —
        # nothing to do.
        return

    # 1. Ensure has_reduction_levels = TRUE on Kemikalieskatt types.
    #    The IS DISTINCT FROM guard skips rows that are already
    #    correct so the migration is a no-op when called repeatedly.
    cr.execute(
        """
        UPDATE excise_tax_type
           SET has_reduction_levels = TRUE
         WHERE id = ANY(%s)
           AND has_reduction_levels IS DISTINCT FROM TRUE
        """,
        (kemikalieskatt_ids,),
    )

    # 2. Ensure unit_basis = 'kg' on Kemikalieskatt types
    #    (defensive — the data file already sets it, but if the
    #    column was added in a later upgrade against an older row
    #    set, NULL would have been the default).
    cr.execute(
        """
        UPDATE excise_tax_type
           SET unit_basis = 'kg'
         WHERE id = ANY(%s)
           AND unit_basis IS DISTINCT FROM 'kg'
        """,
        (kemikalieskatt_ids,),
    )

    # 3. Ensure country_id is set to base.se on Kemikalieskatt
    #    types — only fills in NULLs, doesn't overwrite a custom
    #    country that an accountant might have set.
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = 'base' AND name = 'se'
        """
    )
    se_row = cr.fetchone()
    if se_row:
        cr.execute(
            """
            UPDATE excise_tax_type
               SET country_id = %s
             WHERE id = ANY(%s)
               AND country_id IS NULL
            """,
            (se_row[0], kemikalieskatt_ids),
        )
