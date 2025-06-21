import frappe, erpnext
from frappe import _
from chemical.chemical.doctype.ball_mill_data_sheet.ball_mill_data_sheet import BallMillDataSheet as _BallMillDataSheet
from frappe.utils import nowtime, flt, cint, getdate, get_fullname, get_url_to_form
from erpnext.stock.doctype.item.item import get_item_defaults
from chemical.comments_api import creation_comment,status_change_comment,cancellation_comment,delete_comment


class BallMillDataSheet(_BallMillDataSheet):
	def on_submit(self):
		if self.get('create_stock_entry') == 0:
			create_stock_entry = 0
		else:
			create_stock_entry = 1
		if create_stock_entry:
			se = frappe.new_doc("Stock Entry")
			se.purpose = "Repack"
			se.company = self.company
			se.stock_entry_type = "Repack"
			se.set_posting_time = 1
			se.posting_date = self.date
			se.posting_time = self.posting_time
			se.from_ball_mill = 1
			se.cost_center = self.cost_center
			# se.branch = self.branch
			cost_center = frappe.db.get_value("Company",self.company,"cost_center")
			if hasattr(self,'send_to_party'):
				se.send_to_party = self.send_to_party
			if hasattr(self,'party_type'):
				se.party_type = self.party_type
			if hasattr(self,'party'):
				se.party = self.party

			for row in self.items:
				item = get_item_defaults(row.item_name, self.company)
				item_dict = {
					'item_code': row.item_name,
					's_warehouse': row.source_warehouse,
					'qty': row.qty,
					'basic_rate': row.basic_rate,
					't_warehouse':None,
					'uom':frappe.db.get_value("Item",row.item_name,"stock_uom"),
					'stock_uom':frappe.db.get_value("Item",self.product_name,"stock_uom"),
					'basic_amount': row.basic_amount,
					'cost_center': self.cost_center,
					'batch_no': row.batch_no,
					'concentration':row.concentration,
					'packaging_material':row.packaging_material,
					'packing_size':row.packing_size,
					'no_of_packages':row.no_of_packages,
					"use_serial_batch_fields": True
				}

				se.append('items', item_dict)
			for d in self.packaging:	
				item = get_item_defaults(self.product_name, self.company)
				item_dict = {
					'item_code': self.product_name,
					't_warehouse': d.warehouse or self.warehouse,
					's_warehouse':None,
					'uom':frappe.db.get_value("Item",self.product_name,"stock_uom"),
					'stock_uom':frappe.db.get_value("Item",self.product_name,"stock_uom"),
					'qty': d.qty,
					'packaging_material': d.packaging_material,
					'packing_size': d.packing_size,
					'no_of_packages': d.no_of_packages,
					'lot_no': d.lot_no,
					'concentration': d.concentration or self.concentration,
					'basic_rate': self.per_unit_amount,
					'valuation_rate': self.per_unit_amount,
					'basic_amount': flt(d.qty * self.per_unit_amount),
					'cost_center': self.cost_center,
					'uv_value':self.get("weighted_average_uv_value"),
					"use_serial_batch_fields": True
				}

				se.append('items', item_dict)
			
			for d in self.ball_mill_additional_cost:	
				se.append('additional_costs',{
					'expense_account':d.expense_account ,
					'description': d.description,
					'amount': flt(d.amount),
					'rate':flt(d.amount),
					'qty':1
				})

			se.save()
			se.flags.ignore_validate = True

			# Create one Quality Inspection for the finished item
			finished_item=[]
			for row in se.items:
				if row.is_finished_item:
					finished_item.append(row)
			for data in finished_item:
				if data and data.batch_no:
					# Fetch details from Batch
					batch = frappe.db.get_value("Batch", finished_item.batch_no, 
						["manufacturing_date", "expiry_date"], as_dict=True)

					qi = frappe.new_doc("Quality Inspection")
					qi.inspection_type = "In Process"
					qi.company = self.company
					qi.reference_type = "Stock Entry"
					qi.reference_name = se.name
					qi.item_code = finished_item.item_code
					qi.description = finished_item.description
					qi.party_product_name = finished_item.item_name
					qi.batch_no = finished_item.batch_no
					qi.report_date = self.date
					qi.inspected_by = frappe.session.user
					qi.status = "Accepted"  # You can set to "Pending" if needed

					# Custom fields (assumes these fields exist in Quality Inspection doctype)
					qi.lot_no = finished_item.lot_no
					qi.sample_size = finished_item.qty
					qi.manufacturing_date = batch.manufacturing_date if batch else None
					qi.expiry_date = batch.expiry_date if batch else None

					# # Optional: Load template from Item master
					# template = frappe.db.get_value("Item", finished_item.item_code, "quality_inspection_template")
					# if template:
					# 	qi.quality_inspection_template = template
					# 	qi.populate_quality_inspection_template()

					qi.save()
					
					for item in se.items:
						if (
							item.is_finished_item
							and item.item_code == finished_item.item_code
							and item.batch_no == finished_item.batch_no
						):
							item.quality_inspection = qi.name

					se.save()

				# qi.flags.ignore_validate = True
				# qi.submit()

			# se.submit()
			self.db_set('stock_entry',se.name)
			batch = None
			for row in self.packaging:
				batch_name = frappe.db.sql("""
					SELECT sed.batch_no from `tabStock Entry` se LEFT JOIN `tabStock Entry Detail` sed on (se.name = sed.parent)
					WHERE 
						se.name = '{name}'
						and (sed.t_warehouse != '' or sed.t_warehouse IS NOT NULL) 
						and sed.qty = {qty}
						and sed.packaging_material = '{packaging_material}'
						and sed.packing_size = '{packing_size}'
						and sed.no_of_packages = {no_of_packages}""".format(
							name=se.name,
							qty=row.qty,
							packaging_material=row.packaging_material,
							packing_size=row.packing_size,
							no_of_packages=row.no_of_packages,
						))
				if batch_name:
					batch = batch_name[0][0] or ''

				if batch:
					row.db_set('batch_no', batch)
					if self.customer_name:
						frappe.db.set_value("Batch",batch,'customer',self.customer_name)
					if self.lot_no:
						frappe.db.set_value("Batch",batch,'sample_ref_no',self.lot_no)