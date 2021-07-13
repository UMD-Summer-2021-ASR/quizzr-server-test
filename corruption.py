from typing import Union, List, Tuple


# Generator function that produces dictionaries with each key missing.
# depth is for recursively "shattering" dictionaries. By default, depth is 0, meaning no recursive shattering will take
# place. A depth of 1, for example, also generates dictionaries with its child dictionaries shattered.
# "affected_keys": A "shatter filter" that makes shatter_dict always include keys not in the shatter filter.
#   Could also be "all", "none", or "same_layer".
# "unaffected_keys": Same as "affected_keys" but with keys in the shatter filter.
# Shatter filter: A list of key and/or tuples each containing a key followed by a shatter filter.
def shatter_dict(
        dictionary: dict,
        depth: int = 0,
        affected_keys: Union[str, List[Union[str, Tuple[str, Union[list, str]]]]] = "all",
        unaffected_keys: Union[str, List[Union[str, Tuple[str, Union[list, str]]]]] = "none"):
    # TODO: Test all cases. Make this intuitive.
    for key in dictionary.keys():
        next_dict = dictionary.copy()
        # Leave this key and all subkeys alone.
        if affected_keys == "none" or unaffected_keys == "all" or (type(unaffected_keys) is list and key in unaffected_keys):
            continue

        # Shatter subkeys.
        if depth != 0 and affected_keys != "same_layer" and type(next_dict[key]) is dict:
            deeper_affected_keys = get_sub_filter(affected_keys, key) if type(affected_keys) is list else affected_keys
            deeper_unaffected_keys = get_sub_filter(unaffected_keys, key) if type(unaffected_keys) is list else unaffected_keys

            if deeper_affected_keys:
                for entry in shatter_dict(next_dict[key], depth - 1, deeper_affected_keys, deeper_unaffected_keys):
                    next_dict2 = next_dict.copy()
                    next_dict2[key] = entry
                    yield next_dict2

        # Leave only this key alone.
        if unaffected_keys == "same_layer" or (type(affected_keys) is list and key not in affected_keys):
            continue

        del next_dict[key]
        yield next_dict


def get_sub_filter(this_filter, key):
    for item in this_filter:
        if type(item) is tuple and item[0] == key:
            return item[1]


def main():
    test_dict = {
        "key1": {"foo": {"a": "int", "b": "string", "c": "list"}, "bar": "b", "baz": "c"},
        "key2": {"a": "int", "b": "string", "c": "list"},
        "key3": "value3"
    }
    results = shatter_dict(
        test_dict,
        depth=-1
    )
    for dictionary in results:
        print(dictionary)


if __name__ == '__main__':
    main()
