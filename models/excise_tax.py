# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ExciseTaxType(models.Model):
    """A reusable description of "how this excise tax is computed":
    the per-unit rate, the optional cap, and — as of 19.0.2.0.0 —
    the *unit* the rate is expressed in (kg, litres, …) and the
    country whose excise system this type belongs to.

    The combination of ``unit_basis`` and ``tax_rate`` is what the
    engine hook in ``account_tax._eval_tax_amount_fixed_amount``
    reads to compute the excise. Different excise tax records can
    point at the same type (cf. CHEM E vs CHEM M sharing the same
    "Electronics (High Rate)" / "Major Appliances (Low Rate)"
    structure but with different reporting tags / posting accounts).
    """

    _name = 'excise.tax.type'
    _description = 'Excise Tax Type'

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
    )
    country_id = fields.Many2one(
        'res.country',
        string="Country",
        help="Excise regime this type belongs to. The shipped types "
             "are all Sweden; the field is here so future contributors "
             "can add Finland/Denmark/etc. excise rows without forking "
             "the model.",
        default=lambda self: self.env.ref('base.se', raise_if_not_found=False),
    )
    unit_basis = fields.Selection(
        selection=[
            ('kg', 'Weight in kilograms (kg)'),
            ('liter', 'Volume in litres (L)'),
            # Future: 'tonne', 'liter_pure', 'pcs', 'm3', 'kWh',
            # 'passenger', 'percent_base'. Each one needs its own
            # branch in ``_eval_tax_amount_fixed_amount`` and a
            # matching per-product driver field, so they're added
            # alongside the relevant Phase-2/3/4 tax data.
        ],
        string="Unit Basis",
        default='kg',
        required=True,
        help="Decides which per-product field the tax-engine hook "
             "reads when computing the excise on a line, and what "
             "unit ``Tax Rate`` is expressed in. ``kg`` reads "
             "``net_weight_excise``; ``liter`` reads "
             "``excise_volume_litres``.",
    )
    tax_rate = fields.Float(
        string="Tax Rate",
        digits=(12, 2),
        help="Rate per ``unit_basis`` unit, in SEK (or the country's "
             "currency). E.g. 180.71 SEK per kg for high-rate "
             "Kemikalieskatt; 2020 SEK per litre for regular "
             "nicotine e-liquid.",
    )
    max_limit = fields.Float(
        string="Maximum Limit per Unit",
        digits=(12, 2),
        help="Optional per-unit cap on the computed excise amount "
             "(used by Kemikalieskatt only). 0 = no cap.",
    )
    has_reduction_levels = fields.Boolean(
        string="Has Per-Product Reductions",
        default=False,
        help="When enabled, products taxed with this excise type can "
             "select a reduction level (No / 50% / 90%). Specific to "
             "Kemikalieskatt — products with certain "
             "flame-retardant chemistries qualify for a 50% or 90% "
             "tax reduction. Other excise regimes (Nikotinskatt, "
             "alcohol, gravel, …) don't have this kind of "
             "per-product reduction; leave this off and the "
             "Reduction Level field is hidden on the product form "
             "and the reduction_ratio is ignored by the engine.",
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_excise_taxable = fields.Boolean(string="Excise Taxable")

    excise_tax_type_id = fields.Many2one(
        'excise.tax.type',
        string="Excise Tax Type",
    )

    # ------------------------------------------------------------------
    # Per-unit-basis driver fields. Only the field matching the linked
    # excise type's ``unit_basis`` is read at line creation time and
    # snapshotted onto the order/invoice line. The other fields stay
    # at zero and don't influence anything.
    # ------------------------------------------------------------------
    net_weight_excise = fields.Float(
        string="Excise Tax Weight (kg)",
        help="Weight in kg used for excise tax calculation when the "
             "linked Excise Type's Unit Basis is 'kg' (e.g. "
             "Kemikalieskatt, nicotine pouches).",
    )
    excise_volume_litres = fields.Float(
        string="Excise Tax Volume (L)",
        help="Volume in litres used for excise tax calculation when "
             "the linked Excise Type's Unit Basis is 'liter' (e.g. "
             "nicotine e-liquid).",
    )

    excise_reduction = fields.Selection(
        [
            ('0', 'No Reduction (100%)'),
            ('50', '50% Reduction'),
            ('90', '90% Reduction'),
        ],
        string="Reduction Level",
        default='0',
        help="Per-product reduction applied AFTER the per-unit cap. "
             "Specific to Kemikalieskatt rules (50%/90% for products "
             "containing certain flame-retardants). For other excise "
             "regimes (nicotine, alcohol, …) leave this at 'No "
             "Reduction'.",
    )

    # Mirror of the linked Excise Type's ``unit_basis``. Used by the
    # product form to switch which driver field is visible (kg vs
    # liter). Exposed as a related field so the view can reference
    # it directly with `invisible="excise_unit_basis == 'liter'"`,
    # which works reliably across Odoo 17/18/19 — putting the same
    # condition on `excise_tax_type_id.unit_basis` only sometimes
    # evaluates correctly because Odoo doesn't always pre-fetch
    # nested M2O fields into the form's record.
    excise_unit_basis = fields.Selection(
        related='excise_tax_type_id.unit_basis',
        string="Excise Unit Basis",
        readonly=True,
    )
    excise_has_reduction_levels = fields.Boolean(
        related='excise_tax_type_id.has_reduction_levels',
        string="Excise Has Reductions",
        readonly=True,
    )
