# -*- coding: utf-8 -*-
"""Post-install hooks for the Swedish Excise Tax module."""

import logging

_logger = logging.getLogger(__name__)

# Preferred Swedish BAS codes for the Chemical Tax liability account,
# tried in order. 2616 is the most common custom code for
# "Kemikalieskatt att betala", 2615 is sometimes reused from the reduced
# VAT series, 2640 is the generic "Övrig punktskatt", and 2980 is the
# fallback "Övriga skatteskulder".
_CANDIDATE_CODES = ('2616', '2615', '2640', '2980')


def _find_liability_account(env, company):
    """Return the first existing account.account on the company whose
    code matches our candidate BAS codes, or False if none exist.
    """
    Account = env['account.account'].with_company(company)
    for code in _CANDIDATE_CODES:
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
    """Bind the Swedish Chemical Tax liability account to the tax-type
    repartition lines for every company at install time.

    Safe to run repeatedly: only touches repartition lines that
    currently have account_id=False, so manual customizations are
    preserved across upgrades.
    """
    reps = env['account.tax.repartition.line'].search([
        ('tax_id.amount_type', '=', 'swedish_excise'),
        ('repartition_type', '=', 'tax'),
        ('account_id', '=', False),
    ])
    if not reps:
        return

    # Group by company so we only do one lookup per company, not per
    # repartition line.
    company_account = {}
    for rep in reps:
        company = rep.company_id or rep.tax_id.company_id or env.company
        if company.id not in company_account:
            company_account[company.id] = _find_liability_account(env, company)
        account = company_account[company.id]
        if account:
            rep.account_id = account.id
        else:
            _logger.info(
                "Swedish Excise Tax: no BAS account %s found for company %s; "
                "leaving repartition line %s without an account. An accountant "
                "should assign one manually on the tax form.",
                "/".join(_CANDIDATE_CODES),
                company.display_name,
                rep.id,
            )
