# -*- coding: utf-8 -*-
"""Post-install hooks for the Swedish Excise Tax module."""

import logging

_logger = logging.getLogger(__name__)


# Per-excise-type preferred BAS-code chains. The hook tries each code
# in order and binds the first one that exists on the target
# company's chart of accounts.
#
# - Kemikalieskatt: 2616 ("Kemikalieskatt att betala", custom but
#   common), then 2615 (sometimes reused from the reduced VAT series),
#   then 2640 (Övrig punktskatt), then 2980 (Övriga skatteskulder).
# - Tobaksskatt: 2630 ("Skuld punktskatt tobak"), then 2640, then
#   2980. 2630 is the standard BAS code reserved for tobacco-tax
#   liabilities.
# - Nikotinskatt: there's no widely-accepted custom BAS code for
#   nicotine yet — most accountants use 2640 (Övrig punktskatt) and
#   sub-categorise via reporting tags. Falls back to 2980.
#
# Any swedish_excise tax whose excise_type isn't in this map gets
# the legacy default chain (kemikalie-style); add new categories
# (alcohol → 2620, …) here as Phase 2c / 3 / 4 tax records land.
_CANDIDATES_BY_EXCISE_TYPE_XMLID = {
    'l10n_se_excise_tax.excise_type_electronics':       ('2616', '2615', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_major_appliances':  ('2616', '2615', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_cigarettes': ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_cigars':     ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_snus':       ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_smoking':    ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_chewing':    ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_tobacco_other':      ('2630', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_eliquid':       ('2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_eliquid_high':  ('2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_other':         ('2640', '2980'),
}
_DEFAULT_CANDIDATES = ('2640', '2980')


# ============================================================
# Shipped excise.tax.type data — single source of truth
# ============================================================
# This dict declares the engine-critical and rate fields for every
# excise type the module ships. It's used both at fresh install
# (post_init_hook applies it after the data file has loaded) AND
# at every -u upgrade (the migration in
# migrations/<latest>/post-migration.py re-applies it).
#
# Updating Swedish excise rates after a Skatteverket change
# becomes a tiny three-step process for non-technical contributors:
#
#   1. Edit the rate / cap in this dict (and in
#      data/excise_tax_data.xml so fresh installs see the same).
#   2. Bump the manifest version.
#   3. Copy migrations/<previous>/post-migration.py into a new
#      migrations/<new-version>/ folder. The boilerplate just
#      calls apply_shipped_excise_data(env).
#
# Existing databases that run -u then automatically pick up the
# new rates without any SQL or accountant action.
#
# IMPORTANT — verifying rates before editing this dict.
# Swedish excise rates are set by Skatteverket and re-indexed
# annually. Before you change a value here you should verify the
# current official rate from Skatteverket
# (https://www.skatteverket.se/foretag/skatterochavdrag/punktskatter)
# — not from a secondary source. Wrong rates mean wrong taxes
# on every invoice the module produces.
#
# ENGINE-CRITICAL fields ALWAYS overwrite the live record:
#   - tax_rate, max_limit (Skatteverket-set rates)
#   - unit_basis (engine dispatch driver)
#   - has_reduction_levels (engine reduction gate)
#   - country_id (exemption + tax-totals scoping)
#
# Accountant-overridable fields are NOT in this dict and so are
# never touched by this mechanism: name, description, posting
# account, tag assignments, repartition lines, etc.
# ============================================================
SHIPPED_EXCISE_TAX_TYPES = {
    # ---------- Kemikalieskatt — 2026-01-01 rates ----------
    'l10n_se_excise_tax.excise_type_electronics': {
        'tax_rate': 180.71,
        'max_limit': 552.27,
        'unit_basis': 'kg',
        'has_reduction_levels': True,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_major_appliances': {
        'tax_rate': 12.42,
        'max_limit': 552.27,
        'unit_basis': 'kg',
        'has_reduction_levels': True,
        'country_xmlid': 'base.se',
    },
    # ---------- Tobaksskatt — 2026-01-01 rates ----------
    'l10n_se_excise_tax.excise_type_tobacco_cigarettes': {
        'tax_rate': 2.08,
        'max_limit': 0.0,
        'unit_basis': 'pcs',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_tobacco_cigars': {
        'tax_rate': 1.83,
        'max_limit': 0.0,
        'unit_basis': 'pcs',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_tobacco_snus': {
        'tax_rate': 435.00,
        'max_limit': 0.0,
        'unit_basis': 'kg',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_tobacco_smoking': {
        'tax_rate': 2525.00,
        'max_limit': 0.0,
        'unit_basis': 'kg',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_tobacco_chewing': {
        'tax_rate': 598.00,
        'max_limit': 0.0,
        'unit_basis': 'kg',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_tobacco_other': {
        'tax_rate': 2525.00,
        'max_limit': 0.0,
        'unit_basis': 'kg',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    # ---------- Nikotinskatt — 2026-01-01 rates ----------
    'l10n_se_excise_tax.excise_type_nicotine_eliquid': {
        'tax_rate': 2020.00,
        'max_limit': 0.0,
        'unit_basis': 'liter',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_nicotine_eliquid_high': {
        'tax_rate': 4040.00,
        'max_limit': 0.0,
        'unit_basis': 'liter',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
    'l10n_se_excise_tax.excise_type_nicotine_other': {
        'tax_rate': 202.00,
        'max_limit': 0.0,
        'unit_basis': 'kg',
        'has_reduction_levels': False,
        'country_xmlid': 'base.se',
    },
}


def apply_shipped_excise_data(env):
    """Apply the shipped excise.tax.type values to live records.

    Called from ``post_init_hook`` (fresh installs, after the data
    file has loaded) and from
    ``migrations/<latest-version>/post-migration.py`` (every -u
    upgrade). Idempotent: writing the same value to a record is a
    no-op for Odoo's ORM, so re-running this is safe.

    Only writes engine-critical fields listed in
    ``SHIPPED_EXCISE_TAX_TYPES`` — accountant-editable fields like
    name, posting account, repartition lines, and tag assignments
    are never touched, so customer-side customisations survive
    upgrades.

    Logs at INFO level when a record is updated so the upgrade
    log shows which rates moved.
    """
    Country = env['res.country']
    for xmlid, fields in SHIPPED_EXCISE_TAX_TYPES.items():
        record = env.ref(xmlid, raise_if_not_found=False)
        if not record:
            # Either the module is being installed and the data
            # file hasn't been loaded yet (post_init_hook runs
            # AFTER the data file in Odoo 19, so this shouldn't
            # happen on installs), or this xmlid was renamed /
            # the record manually deleted. Skip silently.
            continue

        update_vals = {
            'tax_rate': fields['tax_rate'],
            'max_limit': fields['max_limit'],
            'unit_basis': fields['unit_basis'],
            'has_reduction_levels': fields['has_reduction_levels'],
        }
        country_xmlid = fields.get('country_xmlid')
        if country_xmlid:
            country = env.ref(country_xmlid, raise_if_not_found=False)
            if country:
                update_vals['country_id'] = country.id

        # Detect whether anything actually changes so the log line
        # only fires when it's worth seeing. Many2one fields like
        # ``country_id`` show up in ``update_vals`` as the FK integer
        # (``country.id``) but ``record[key]`` returns a recordset —
        # comparing those directly emits a ``UserWarning`` in Odoo 19
        # ("unsupported operand type(s) for '==': 'res.country()' ==
        # '196'") and is always truthy, which makes the log report
        # spurious changes on every upgrade. Normalise to an int for
        # the comparison.
        def _current(field_name):
            value = record[field_name]
            # Recordsets expose ``.id`` (singleton) or are empty
            # (``not value`` → ``False``, equivalent to id 0 here).
            if hasattr(value, '_name'):
                return value.id or False
            return value
        changed = {
            key: value
            for key, value in update_vals.items()
            if _current(key) != value
        }
        if changed:
            record.sudo().write(update_vals)
            _logger.info(
                "Swedish Excise Tax: refreshed shipped values on "
                "%s (xmlid=%s); changes=%s",
                record.display_name, xmlid, changed,
            )


def _candidate_codes_for(env, tax):
    """Return the BAS-code candidate chain for a swedish_excise tax,
    based on the linked excise_type_id's xmlid.

    Falls back to a generic chain when the type isn't explicitly
    mapped (e.g., a partner module added a new excise.tax.type).
    """
    excise_type = tax.excise_type_id
    if not excise_type:
        return _DEFAULT_CANDIDATES
    xmlid_data = env['ir.model.data'].sudo().search([
        ('model', '=', 'excise.tax.type'),
        ('res_id', '=', excise_type.id),
    ], limit=1)
    if xmlid_data:
        full_xmlid = f"{xmlid_data.module}.{xmlid_data.name}"
        return _CANDIDATES_BY_EXCISE_TYPE_XMLID.get(
            full_xmlid, _DEFAULT_CANDIDATES,
        )
    return _DEFAULT_CANDIDATES


def _find_liability_account(env, company, codes):
    """Return the first existing account.account on the company whose
    code matches ``codes`` (in order), or False if none exist.
    """
    Account = env['account.account'].with_company(company)
    for code in codes:
        # In Odoo 17+, account.account became multi-company via
        # company_ids (Many2many). Search both attr names to be
        # compatible with older minor versions too.
        domain = [('code', '=', code)]
        if 'company_ids' in Account._fields:
            domain.append(('company_ids', 'in', company.ids))
        else:  # pragma: no cover - legacy
            domain.append(('company_id', '=', company.id))
        account = Account.search(domain, limit=1)
        if account:
            return account
    return False


def post_init_hook(env):
    """Bind the Swedish Excise Tax liability account to the tax-type
    repartition lines for every company at install time.

    Safe to run repeatedly: only touches repartition lines that
    currently have ``account_id=False``, so manual customisations are
    preserved across upgrades.

    Per-excise-type candidate chains live in
    ``_CANDIDATES_BY_EXCISE_TYPE_XMLID`` — Kemikalieskatt prefers
    2616, Nikotinskatt prefers 2640.
    """
    # Re-assert the shipped engine-critical fields on every install /
    # upgrade so accountants always see the rates the module currently
    # ships with — see SHIPPED_EXCISE_TAX_TYPES at the top of this
    # file for the source of truth and the workflow for updating
    # rates after a Skatteverket change.
    apply_shipped_excise_data(env)

    reps = env['account.tax.repartition.line'].search([
        ('tax_id.amount_type', '=', 'swedish_excise'),
        ('repartition_type', '=', 'tax'),
        ('account_id', '=', False),
    ])
    if not reps:
        return

    # Cache per (company.id, excise_type.id) so we don't re-search the
    # same chart of accounts more than once.
    cache = {}
    for rep in reps:
        company = rep.company_id or rep.tax_id.company_id or env.company
        cache_key = (company.id, rep.tax_id.excise_type_id.id)
        if cache_key not in cache:
            codes = _candidate_codes_for(env, rep.tax_id)
            cache[cache_key] = (codes, _find_liability_account(env, company, codes))
        codes, account = cache[cache_key]
        if account:
            rep.account_id = account.id
        else:
            _logger.info(
                "Swedish Excise Tax: no BAS account %s found for company %s "
                "(tax %s); leaving repartition line %s without an account. "
                "An accountant should assign one manually on the tax form.",
                "/".join(codes),
                company.display_name,
                rep.tax_id.display_name,
                rep.id,
            )
