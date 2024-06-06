from erpnext.accounts.doctype.tax_withholding_category.tax_withholding_category import get_cost_center, get_party_details, get_tax_amount, get_tax_row_for_tcs, get_tax_withholding_details
import frappe
import erpnext
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry as _PaymentEntry
from frappe.utils.data import flt

class PaymentEntry(_PaymentEntry):
	def set_tax_withholding(self):
		if not self.party_type == "Supplier":
			return

		if not self.apply_tax_withholding_amount:
			return

		order_amount = self.get_order_net_total()

		net_total = flt(order_amount) + flt(self.unallocated_amount)

		# Adding args as purchase invoice to get TDS amount
		args = frappe._dict(
			{
				"company": self.company,
				"doctype": "Payment Entry",
				"supplier": self.party,
				"posting_date": self.posting_date,
				"net_total": net_total,
			}
		)

		tax_withholding_details = get_party_tax_withholding_details(args, self.tax_withholding_category)

		if not tax_withholding_details:
			return

		tax_withholding_details.update(
			{"cost_center": self.cost_center or erpnext.get_default_cost_center(self.company)}
		)

		accounts = []
		for d in self.taxes:
			if d.account_head == tax_withholding_details.get("account_head"):
				# Preserve user updated included in paid amount
				if d.included_in_paid_amount:
					tax_withholding_details.update({"included_in_paid_amount": d.included_in_paid_amount})

				d.update(tax_withholding_details)
			accounts.append(d.account_head)

		if not accounts or tax_withholding_details.get("account_head") not in accounts:
			self.append("taxes", tax_withholding_details)

		to_remove = [
			d
			for d in self.taxes
			if not d.tax_amount and d.account_head == tax_withholding_details.get("account_head")
		]

		for d in to_remove:
			self.remove(d)

def get_party_tax_withholding_details(inv, tax_withholding_category=None):
	if inv.doctype == "Payment Entry":
		inv.tax_withholding_net_total = inv.net_total

	pan_no = ""
	parties = []
	party_type, party = get_party_details(inv)
	has_pan_field = frappe.get_meta(party_type).has_field("pan")

	if not tax_withholding_category:
		if has_pan_field:
			fields = ["tax_withholding_category", "pan"]
		else:
			fields = ["tax_withholding_category"]

		tax_withholding_details = frappe.db.get_value(party_type, party, fields, as_dict=1)

		tax_withholding_category = tax_withholding_details.get("tax_withholding_category")
		pan_no = tax_withholding_details.get("pan")

	if not tax_withholding_category:
		return

	# if tax_withholding_category passed as an argument but not pan_no
	if not pan_no and has_pan_field:
		pan_no = frappe.db.get_value(party_type, party, "pan")

	# Get others suppliers with the same PAN No
	if pan_no:
		parties = frappe.get_all(party_type, filters={"pan": pan_no}, pluck="name")

	if not parties:
		parties.append(party)

	posting_date = inv.get("posting_date") or inv.get("transaction_date")
	tax_details = get_tax_withholding_details(tax_withholding_category, posting_date, inv.company)

	if not tax_details:
		frappe.throw(
			_("Please set associated account in Tax Withholding Category {0} against Company {1}").format(
				tax_withholding_category, inv.company
			)
		)

	if party_type == "Customer" and not tax_details.cumulative_threshold:
		# TCS is only chargeable on sum of invoiced value
		frappe.throw(
			_(
				"Tax Withholding Category {} against Company {} for Customer {} should have Cumulative Threshold value."
			).format(tax_withholding_category, inv.company, party)
		)

	tax_amount, tax_deducted, tax_deducted_on_advances, voucher_wise_amount = get_tax_amount(
		party_type, parties, inv, tax_details, posting_date, pan_no
	)

	if party_type == "Supplier":
		tax_row = get_tax_row_for_tds(tax_details, tax_amount)
	else:
		tax_row = get_tax_row_for_tcs(inv, tax_details, tax_amount, tax_deducted)

	cost_center = get_cost_center(inv)
	tax_row.update({"cost_center": cost_center})

	if inv.doctype == "Purchase Invoice":
		return tax_row, tax_deducted_on_advances, voucher_wise_amount
	else:
		return tax_row
	
def get_tax_row_for_tds(tax_details, tax_amount):
	return {
		"category": "Total",
		"charge_type": "Actual",
		"tax_amount": tax_amount,
		# "add_deduct_tax": "Deduct",#finbyz changes
		"description": tax_details.description,
		"account_head": tax_details.account_head,
	}

