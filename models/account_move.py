# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    """Helper that applies the Swedish-excise fold to ``tax_totals``
    on demand for customer-facing rendering. See the matching docstring
    on ``sale.order._l10n_se_get_tax_totals_for_render`` for the
    rationale (form view shows the full breakdown; PDF / portal
    respect the company flag).
    """

    _inherit = 'account.move'

    def _l10n_se_get_tax_totals_for_render(self):
        self.ensure_one()
        return self.env['account.tax']._l10n_se_excise_postprocess_tax_totals(
            self.tax_totals,
            fold_excise=not self.company_id.excise_show_as_separate_row,
        )
