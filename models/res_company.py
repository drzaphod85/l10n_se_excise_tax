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

    hide_vat_column_on_documents = fields.Boolean(
        string="Hide VAT Column on Documents",
        default=False,
        help="Hide the per-line VAT / Moms / Taxes column (the one "
             "showing labels like '25% G, CHEM E') on quotations, "
             "sales orders and invoices when rendered as PDF or on "
             "the customer portal. The VAT row in the totals block "
             "stays visible in every case so the statutory VAT "
             "amount and rate are still disclosed. On the order / "
             "invoice form views the column is always visible but "
             "can be toggled from the column picker as usual.",
    )
