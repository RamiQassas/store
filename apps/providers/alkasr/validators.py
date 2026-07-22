class AlkasrValidator:
    @staticmethod
    def validate_quantity(qty, product_type, qty_min, qty_max, qty_list):
        if product_type == "package":
            if qty != 1:
                return False, "الكمية يجب أن تكون 1."
        elif product_type == "amount":
            if qty_min and qty < qty_min:
                return False, f"الحد الأدنى للكمية هو {qty_min}."
            if qty_max and qty > qty_max:
                return False, f"الحد الأقصى للكمية هو {qty_max}."
        elif product_type == "fixed_quantities":
            if str(qty) not in [str(x) for x in qty_list]:
                return False, f"الكمية غير مسموح بها. القيم المسموحة: {', '.join(str(x) for x in qty_list)}"
        elif product_type == "category_only":
            return False, "هذا تصنيف ولا يمكن شراؤه."
            
        return True, ""
