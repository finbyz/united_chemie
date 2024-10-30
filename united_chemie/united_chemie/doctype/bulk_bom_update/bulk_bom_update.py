# Copyright (c) 2024, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

# import frappe
from frappe import db  
from frappe.model.document import Document
import frappe
from frappe import _
from frappe.utils import flt
from chemical.chemical.doc_events.bom import update_bom_cost
from chemical.chemical.doc_events.bom import _update_bom_cost
from chemical.chemical.doc_events.bom import cost_calculation
from chemical.chemical.doc_events.bom import upadte_item_price

class BulkBOMUpdate(Document):
    
    @frappe.whitelist()
    def get_bom_details(self,item_code=None, item_group=None):
        conditions = []

        if item_group:
            conditions.append(f"i.item_group = '{item_group}'")
        elif item_code:
            conditions.append(f"b.item = '{item_code}'")


        if not conditions:
            frappe.throw("Please select either Item Code or Item Group.")

        condition_str = " AND ".join(conditions)
        company = self.company

        query = f"""
            SELECT
                b.name AS bom, b.item AS item_code
            FROM `tabBOM` AS b
            JOIN `tabItem` AS i ON i.name = b.item
            WHERE {condition_str} AND b.is_active = 1 AND b.company = '{company}'
        """
        return frappe.db.sql(query, as_dict=True)

    def on_submit(self):
        if not self.bom_details:
            frappe.throw(_("No BOM details found to process."))

        for bom_detail in self.bom_details:
            if not bom_detail.bom:
                frappe.throw(_("Please specify a BOM reference in BOM details."))

            bom_doc = frappe.get_doc("BOM", bom_detail.bom)
            bom_doc.additional_cost = []
            
            for cost in self.additional_cost:
                bom_doc.append("additional_cost", {
                    "description": cost.description,
                    "qty": cost.qty,
                    "uom": cost.uom,
                    "rate": cost.rate,
                    "amount": flt(flt(cost.qty) * flt(cost.rate)),
                })

            
            bom_doc.flags.ignore_validate_update_after_submit = True
            bom_doc.save()

            frappe.msgprint(_("Additional costs added to BOM {0}").format(bom_detail.bom))
            update_bom_cost(bom_doc.name)
            cost_calculation(bom_doc)
