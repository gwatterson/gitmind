def shipping_cost(country: str, weight_kg: float, express: bool, member: bool) -> float:
    if country == "IT":
        if weight_kg < 1:
            if express:
                if member:
                    return 4.0
                else:
                    return 7.5
            else:
                if member:
                    return 0.0
                else:
                    return 3.9
        else:
            if express:
                if member:
                    return 6.0
                else:
                    return 12.0
            else:
                return 5.9 if not member else 2.0
    else:
        if express:
            return 25.0 if not member else 18.0
        return 14.0 if weight_kg > 2 else 9.0
