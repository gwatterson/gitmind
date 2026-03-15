"""
Test file with intentional QUALITY issues.
Used for testing GitMind's quality analysis agent.

Issues:
  - Deeply nested conditionals (cyclomatic complexity > 15)
  - Long function with too many parameters
  - Poor naming conventions
"""


def process_data(data, flag1, flag2, flag3, mode, extra):
    """Process data with extremely high cyclomatic complexity."""
    if flag1:
        if data:
            if flag2:
                if mode == "a":
                    if flag3:
                        if extra:
                            for item in data:
                                if item > 0:
                                    if item < 100:
                                        result = item * 2
                                    else:
                                        result = item
                                else:
                                    result = 0
                        else:
                            result = -1
                    else:
                        result = -2
                elif mode == "b":
                    result = sum(data)
                else:
                    result = 0
            else:
                result = len(data)
        else:
            result = None
    else:
        result = False
    return result


def x(a, b, c, d, e, f, g, h, i, j):
    """Terrible function name, too many parameters, no documentation."""
    t = 0
    for q in range(a):
        for w in range(b):
            for r in range(c):
                t += q * w * r
    if d:
        t += e
    elif f:
        t -= g
    else:
        t = h + i + j
    return t
