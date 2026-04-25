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
# - Nikotinskatt: there's no widely-accepted custom BAS code for
#   nicotine yet — most accountants use 2640 (Övrig punktskatt) and
#   sub-categorise via reporting tags. Falls back to 2980.
#
# Any swedish_excise tax whose excise_type isn't in this map gets
# the legacy default chain (kemikalie-style); add new categories
# (alcohol → 2620, tobacco → 2630, …) here as Phase 2/3/4 tax
# records land.
_CANDIDATES_BY_EXCISE_TYPE_XMLID = {
    'l10n_se_excise_tax.excise_type_electronics':       ('2616', '2615', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_major_appliances':  ('2616', '2615', '2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_eliquid':       ('2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_eliquid_high':  ('2640', '2980'),
    'l10n_se_excise_tax.excise_type_nicotine_other':         ('2640', '2980'),
}
_DEFAULT_CANDIDATES = ('2640', '2980')


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
