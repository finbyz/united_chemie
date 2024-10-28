// Copyright (c) 2024, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bulk BOM Update', {
    fetch_details: function(frm) {
	
		if (frm.doc.item_code || frm.doc.item_group) {
			frm.doc.bom_details = [];  
	
			frm.call({
				doc: frm.doc,
				method: "get_bom_details",
				args: {
					item_code: frm.doc.item_code,
					item_group: frm.doc.item_group
				},
			}).then((r) => {
				if (r.message) {
					console.log(r.message);
					r.message.forEach(element => {
						var bom_entry = frm.add_child("bom_details");
						bom_entry.bom = element['bom'];
						bom_entry.item_code = element['item_code'];
					});
					frm.refresh_field("bom_details");
				}
			});
		} else {
			frappe.msgprint("Please select either Item Code or Item Group.");
		}
	}	
});

frappe.ui.form.on("BOM Additional Cost", {
	rate: function(frm, cdt, cdn){
		let d = locals[cdt][cdn]
		frappe.model.set_value(d.doctype,d.name,'amount',flt(d.qty*d.rate))
        frm.refresh_field('additional_cost');
    },
});

