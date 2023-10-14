import re
import math
# a = "hello %$      world %^& let      me ^@ love && you"
# print(re.findall(r'\w+',a))

# List = [1, 2, 3, 4, 5, 6, 7, 8, 9]
# print(List[3:8])

# test = 2.14
# print(math.ceil(test))

# test_list = {1,2,3,4,5,6,7,8,9}
# other_list = [1,2,3,4]
# temp = set()
# for item in other_list:
#     if item in test_list:
#         temp.add(item)
# test_list = set()
# print(temp)
# print(test_list)

test = "ingredients chili oil"

test= test.replace("ingredients", "")
print(test)