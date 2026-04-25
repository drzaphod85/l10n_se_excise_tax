# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Expose the company-level excise display toggles on the standard
    Accounting settings page so an administrator can switch them
    without opening the company record directly.
    """

    _inherit = 'res.config.settings'

    excise_show_as_separate_row = fields.Boolean(
        related='company_id.excise_show_as_separate_row',
        readonly=False,
    )
    hide_vat_column_on_documents = fields.Boolean(
        related='company_id.hide_vat_column_on_documents',
        readonly=False,
    )
