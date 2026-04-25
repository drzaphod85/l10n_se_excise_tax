# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    """Helper that applies the Swedish-excise fold to ``tax_totals``
    on demand for customer-facing rendering.

    Earlier versions applied the fold inside ``_compute_tax_totals``,
    which made the on-screen form-view widget also render the folded
    view. Internal users found that confusing — the form view is the
    seller's working surface and benefits from showing the full
    breakdown at all times. This method moves the fold to the QWeb
    layer instead: the standard ``tax_totals`` field always returns
    the full breakdown, and the QWeb inherits in
    ``views/report_templates.xml`` call this helper from their
    ``<t t-set="tax_totals" ... />`` so PDF / portal still respect
    the company's ``excise_show_as_separate_row`` flag.
    """

    _inherit = 'sale.order'

    def _l10n_se_get_tax_totals_for_render(self):
        """Return ``tax_totals`` with the excise fold applied per
        ``company.excise_show_as_separate_row``.

        Called from QWeb only — never used by the on-screen widget.
        """
        self.ensure_one()
        return self.env['account.tax']._l10n_se_excise_postprocess_tax_totals(
            self.tax_totals,
            fold_excise=not self.company_id.excise_show_as_separate_row,
        )
