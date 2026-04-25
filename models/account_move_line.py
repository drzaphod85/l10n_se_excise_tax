# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    excise_weight = fields.Float(
        string="Skattevikt (Snapshot)",
        digits='Stock Weight',
        help="Vikt (kg) som används för beräkning vid faktureringstillfället. "
             "Konsulteras endast när skattetypens enhet är 'kg'.",
    )
    excise_volume = fields.Float(
        string="Skattevolym (Snapshot)",
        digits=(12, 4),
        help="Volym (L) som används för beräkning vid faktureringstillfället. "
             "Konsulteras endast när skattetypens enhet är 'liter'.",
    )
    excise_reduction_ratio = fields.Float(
        string="Avdragsfaktor",
        default=1.0,
        help="Reduktionsfaktor (1.0, 0.5 eller 0.1) vid faktureringstillfället. "
             "Specifik för Kemikalieskatt; ignoreras av andra punktskattetyper.",
    )

    # ------------------------------------------------------------------
    # Display helpers for the "excise folded into the line price" mode.
    # See the matching block on ``sale.order.line`` for the rationale.
    # ------------------------------------------------------------------
    excise_unit_amount = fields.Monetary(
        string="Excise (per unit)",
        compute='_compute_l10n_se_excise_display',
        help="Per-unit Swedish excise amount for this line, computed from "
             "the snapshot weight and reduction ratio. 0 when no excise "
             "tax is applied.",
    )
    l10n_se_display_price_unit = fields.Monetary(
        string="Unit Price (display)",
        compute='_compute_l10n_se_excise_display',
    )
    l10n_se_display_price_subtotal = fields.Monetary(
        string="Amount (display)",
        compute='_compute_l10n_se_excise_display',
    )

    @api.depends(
        'price_unit', 'price_subtotal', 'quantity',
        'tax_ids.amount_type', 'tax_ids.excise_type_id',
        'tax_ids.excise_type_id.unit_basis',
        'excise_weight', 'excise_volume', 'excise_reduction_ratio',
        'move_id.company_id.excise_show_as_separate_row',
        'move_id.company_id.country_id',
        'move_id.partner_id.l10n_se_approved_warehouse_keeper',
        'move_id.partner_id.country_id',
    )
    def _compute_l10n_se_excise_display(self):
        for line in self:
            excise_tax = line.tax_ids.filtered(
                lambda t: t.amount_type == 'swedish_excise'
            )[:1]
            per_unit = 0.0
            if excise_tax:
                partner = line.move_id.partner_id
                company = line.move_id.company_id
                exempt = bool(
                    partner
                    and company
                    and partner._l10n_se_is_excise_exempt(company)
                )
                if not exempt:
                    per_unit = excise_tax._get_excise_unit_amount(
                        weight=line.excise_weight or 0.0,
                        volume=line.excise_volume or 0.0,
                        reduction_ratio=line.excise_reduction_ratio or 1.0,
                    )
            line.excise_unit_amount = per_unit
            fold = not (line.move_id.company_id.excise_show_as_separate_row
                        if line.move_id else True)
            if fold and per_unit:
                line_excise = (line.quantity or 0.0) * per_unit
                line.l10n_se_display_price_unit = line.price_unit + per_unit
                line.l10n_se_display_price_subtotal = (
                    line.price_subtotal + line_excise
                )
            else:
                line.l10n_se_display_price_unit = line.price_unit
                line.l10n_se_display_price_subtotal = line.price_subtotal

    @api.onchange('product_id')
    def _onchange_product_id_excise(self):
        mapping = {'0': 1.0, '50': 0.5, '90': 0.1}
        for line in self:
            product = line.product_id
            if product and product.is_excise_taxable:
                line.excise_weight = product.net_weight_excise
                line.excise_volume = product.excise_volume_litres
                line.excise_reduction_ratio = mapping.get(
                    product.excise_reduction, 1.0,
                )
            else:
                line.excise_weight = 0.0
                line.excise_volume = 0.0
                line.excise_reduction_ratio = 1.0

    # ------------------------------------------------------------------
    # Tax-engine integration
    # ------------------------------------------------------------------
    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Same as sale.order.line – propagate the per-line excise
        snapshot into the tax recordset context so account.tax can
        compute the correct amount for this invoice line.

        Also filters the swedish_excise tax out of
        ``base_line['tax_ids']`` for partners that are AWKs or
        based in a different country than the company (see
        ``res.partner._l10n_se_is_excise_exempt``). The line's
        stored ``tax_ids`` are not touched.
        """
        base_line = super()._prepare_base_line_for_taxes_computation(**kwargs)
        excise_taxes = self.tax_ids.filtered(
            lambda t: t.amount_type == 'swedish_excise'
        )
        if not excise_taxes:
            return base_line

        partner = self.move_id.partner_id
        company = self.move_id.company_id
        if partner and partner._l10n_se_is_excise_exempt(company):
            if base_line.get('tax_ids'):
                base_line['tax_ids'] = base_line['tax_ids'].filtered(
                    lambda t: t.amount_type != 'swedish_excise'
                )
            return base_line

        excise_ctx = {
            'excise_line_vals': {
                'excise_weight': self.excise_weight or 0.0,
                'excise_volume': self.excise_volume or 0.0,
                'excise_reduction_ratio': self.excise_reduction_ratio or 1.0,
            },
        }
        if base_line.get('tax_ids'):
            base_line['tax_ids'] = base_line['tax_ids'].with_context(**excise_ctx)
        base_line.update(excise_ctx['excise_line_vals'])
        return base_line
