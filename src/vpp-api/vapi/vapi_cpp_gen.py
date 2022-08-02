#!/usr/bin/env python3

import argparse
import os
import sys
import logging
from vapi_c_gen import CField, CEnum, CStruct, CSimpleType, CStructType,\
    CMessage, json_to_c_header_name, CAlias
from vapi_json_parser import JsonParser


class CppField(CField):
    pass


class CppStruct(CStruct):
    pass


class CppEnum(CEnum):
    pass


class CppAlias(CAlias):
    pass


class CppSimpleType (CSimpleType):
    pass


class CppStructType (CStructType, CppStruct):
    pass


class CppMessage (CMessage):
    def get_swap_to_be_template_instantiation(self):
        return "\n".join(
            [
                f"template <> inline void vapi_swap_to_be<{self.get_c_name()}>({self.get_c_name()} *msg)",
                "{",
                f"  {self.get_swap_to_be_func_name()}(msg);",
                "}",
            ]
        )

    def get_swap_to_host_template_instantiation(self):
        return "\n".join(
            [
                f"template <> inline void vapi_swap_to_host<{self.get_c_name()}>({self.get_c_name()} *msg)",
                "{",
                f"  {self.get_swap_to_host_func_name()}(msg);",
                "}",
            ]
        )

    def get_alloc_template_instantiation(self):
        return "\n".join(
            [
                (
                    "template <> inline %s* vapi_alloc<%s%s>"
                    "(Connection &con%s)"
                    % (
                        self.get_c_name(),
                        self.get_c_name(),
                        ", size_t" * len(self.get_alloc_vla_param_names()),
                        "".join(
                            [
                                f", size_t {n}"
                                for n in self.get_alloc_vla_param_names()
                            ]
                        ),
                    )
                ),
                "{",
                (
                    "  %s* result = %s(con.vapi_ctx%s);"
                    % (
                        self.get_c_name(),
                        self.get_alloc_func_name(),
                        "".join(
                            [f", {n}" for n in self.get_alloc_vla_param_names()]
                        ),
                    )
                ),
                "#if VAPI_CPP_DEBUG_LEAKS",
                "  con.on_shm_data_alloc(result);",
                "#endif",
                "  return result;",
                "}",
            ]
        )

    def get_cpp_name(self):
        return f"{self.name[0].upper()}{self.name[1:]}"

    def get_req_template_name(self):
        template = "Dump" if self.reply_is_stream else "Request"
        return f'{template}<{self.get_c_name()}, {self.reply.get_c_name()}{"".join([", size_t"] * len(self.get_alloc_vla_param_names()))}>'

    def get_req_template_instantiation(self):
        return f"template class {self.get_req_template_name()};"

    def get_type_alias(self):
        return f"using {self.get_cpp_name()} = {self.get_req_template_name()};"

    def get_reply_template_name(self):
        return f"Msg<{self.get_c_name()}>"

    def get_reply_type_alias(self):
        return f"using {self.get_cpp_name()} = {self.get_reply_template_name()};"

    def get_msg_class_instantiation(self):
        return f"template class Msg<{self.get_c_name()}>;"

    def get_get_msg_id_t_instantiation(self):
        return "\n".join(
            [
                f"template <> inline vapi_msg_id_t vapi_get_msg_id_t<{self.get_c_name()}>()",
                "{",
                f"  return ::{self.get_msg_id_name()}; ",
                "}",
                "",
                "template <> inline vapi_msg_id_t "
                "vapi_get_msg_id_t<Msg<%s>>()" % self.get_c_name(),
                "{",
                f"  return ::{self.get_msg_id_name()}; ",
                "}",
            ]
        )

    def get_cpp_constructor(self):
        return '\n'.join(
            [
                'static void __attribute__((constructor)) '
                '__vapi_cpp_constructor_%s()' % self.name,
                '{',
                f'  vapi::vapi_msg_set_msg_id<{self.get_c_name()}>({self.get_msg_id_name()});',
                '}',
            ]
        )


def gen_json_header(parser, logger, j, io, gen_h_prefix, add_debug_comments):
    logger.info("Generating header `%s'" % io.name)
    orig_stdout = sys.stdout
    sys.stdout = io
    d, f = os.path.split(j)
    include_guard = "__included_hpp_%s" % (
        f.replace(".", "_").replace("/", "_").replace("-", "_"))
    print(f"#ifndef {include_guard}")
    print(f"#define {include_guard}")
    print("")
    print("#include <vapi/vapi.hpp>")
    print(f"#include <{gen_h_prefix}{json_to_c_header_name(f)}>")
    print("")
    print("namespace vapi {")
    print("")
    for m in parser.messages_by_json[j].values():
        # utility functions need to go first, otherwise internal instantiation
        # causes headaches ...
        if add_debug_comments:
            print("/* m.get_swap_to_be_template_instantiation() */")
        print(f"{m.get_swap_to_be_template_instantiation()}")
        print("")
        if add_debug_comments:
            print("/* m.get_swap_to_host_template_instantiation() */")
        print(f"{m.get_swap_to_host_template_instantiation()}")
        print("")
        if add_debug_comments:
            print("/* m.get_get_msg_id_t_instantiation() */")
        print(f"{m.get_get_msg_id_t_instantiation()}")
        print("")
        if add_debug_comments:
            print("/* m.get_cpp_constructor() */")
        print(f"{m.get_cpp_constructor()}")
        print("")
        if not m.is_reply and not m.is_event:
            if add_debug_comments:
                print("/* m.get_alloc_template_instantiation() */")
            print(f"{m.get_alloc_template_instantiation()}")
            print("")
        if add_debug_comments:
            print("/* m.get_msg_class_instantiation() */")
        print(f"{m.get_msg_class_instantiation()}")
        print("")
        if m.is_reply or m.is_event:
            if add_debug_comments:
                print("/* m.get_reply_type_alias() */")
            print(f"{m.get_reply_type_alias()}")
            continue
        if add_debug_comments:
            print("/* m.get_req_template_instantiation() */")
        print(f"{m.get_req_template_instantiation()}")
        print("")
        if add_debug_comments:
            print("/* m.get_type_alias() */")
        print(f"{m.get_type_alias()}")
        print("")
    print("}")  # namespace vapi

    print("#endif")
    sys.stdout = orig_stdout


def json_to_cpp_header_name(json_name):
    if json_name.endswith(".json"):
        return f"{os.path.splitext(json_name)[0]}.vapi.hpp"
    raise Exception("Unexpected json name `%s'!" % json_name)


def gen_cpp_headers(parser, logger, prefix, gen_h_prefix, remove_path,
                    add_debug_comments=False):
    prefix = "" if prefix == "" or prefix is None else f"{prefix}/"
    gen_h_prefix = "" if gen_h_prefix is None else f"{gen_h_prefix}/"
    for j in parser.json_files:
        if remove_path:
            d, f = os.path.split(j)
        else:
            f = j
        with open(f'{prefix}{json_to_cpp_header_name(f)}', "w") as io:
            gen_json_header(parser, logger, j, io,
                            gen_h_prefix, add_debug_comments)


if __name__ == '__main__':
    try:
        verbose = int(os.getenv("V", 0))
    except:
        verbose = 0

    if verbose >= 2:
        log_level = 10
    elif verbose == 1:
        log_level = 20
    else:
        log_level = 40

    logging.basicConfig(stream=sys.stdout, level=log_level)
    logger = logging.getLogger("VAPI CPP GEN")
    logger.setLevel(log_level)

    argparser = argparse.ArgumentParser(description="VPP C++ API generator")
    argparser.add_argument('files', metavar='api-file', action='append',
                           type=str, help='json api file'
                           '(may be specified multiple times)')
    argparser.add_argument('--prefix', action='store', default=None,
                           help='path prefix')
    argparser.add_argument('--gen-h-prefix', action='store', default=None,
                           help='generated C header prefix')
    argparser.add_argument('--remove-path', action='store_true',
                           help='remove path from filename')
    args = argparser.parse_args()

    jsonparser = JsonParser(logger, args.files,
                            simple_type_class=CppSimpleType,
                            struct_type_class=CppStructType,
                            field_class=CppField,
                            enum_class=CppEnum,
                            message_class=CppMessage,
                            alias_class=CppAlias)

    gen_cpp_headers(jsonparser, logger, args.prefix, args.gen_h_prefix,
                    args.remove_path)

    for e in jsonparser.exceptions:
        logger.warning(e)
