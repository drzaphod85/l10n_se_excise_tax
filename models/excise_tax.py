from odoo import models, fields, api, _

class ExciseTaxType(models.Model):
    _name = 'excise.tax.type'
    _description = 'Excise Tax Type'

    name = fields.Char(string="Name", required=True, translate=True)
    tax_rate = fields.Float(string="Tax Rate (SEK/kg)", digits=(12, 2))
    max_limit = fields.Float(string="Maximum Limit per Unit", digits=(12, 2))

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_excise_taxable = fields.Boolean(string="Excise Taxable")
    
    excise_tax_type_id = fields.Many2one(
        'excise.tax.type', 
        string="Excise Tax Type"
    )
    
    net_weight_excise = fields.Float(
        string="Excise Tax Weight (kg)",
        help="The weight used specifically for excise tax calculation."
    )
    
    excise_reduction = fields.Selection([
        ('0', 'No Reduction (100%)'),
        ('50', '50% Reduction'),
        ('90', '90% Reduction')
    ], string="Reduction Level", default='0')