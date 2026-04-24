# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    """Company-level toggles that control how Swedish excise tax and
    VAT are rendered on customer-facing documents (quotations, sales
    orders, invoices, their PDF exports, and the customer portal).

    The underlying tax *computation* is unchanged by these flags — VAT
    and excise still post to the correct accounts and Skatteverket tags.
    What changes is only the ``tax_totals`` JSON served to the
    ``account_tax_totals`` widget, which every renderer (form view,
    QWeb PDF, portal template) reads from.
    """

    _inherit = 'res.company'

    excise_show_as_separate_row = fields.Boolean(
        string="Show Excise Tax as Separate Row",
        default=True,
        help="When enabled, the Swedish excise tax appears on its own "
             "row between Untaxed Amount and VAT on quotations, sales "
             "orders, invoices and their PDF / portal renderings. "
             "When disabled, the excise amount is folded into the "
             "Untaxed Amount so the customer does not see a separate "
             "line (the VAT base and the total stay identical).",
    )

    hide_vat_row_on_quotations = fields.Boolean(
        string="Hide VAT Row on Quotations",
        default=False,
        help="Hide the VAT / moms row in the totals block of "
             "quotations and sales orders (on-screen widget, PDF and "
             "customer portal). Useful for B2C price presentation "
             "before an invoice is issued. Posted invoices always "
             "show the VAT row regardless of this setting, as "
             "Mervärdesskattelagen 11 kap. 8 § requires a final "
             "invoice to disclose the VAT amount and rate separately. "
             "VAT is still calculated and posted in the background.",
    )
