#!/usr/bin/env python3

import argparse
import os
import sys
import logging
from vapi_json_parser import Field, Struct, Enum, Union, Message, JsonParser,\
    SimpleType, StructType, Alias


class CField(Field):
    def get_c_name(self):
        return f"vapi_type_{self.name}"

    def get_c_def(self):
        if self.type.get_c_name() == 'vl_api_string_t':
            return (
                "u8 %s[%d];" % (self.name, self.len)
                if self.len
                else f"vl_api_string_t {self.name};"
            )

        if self.len is not None and type(self.len) != dict:
            return "%s %s[%d];" % (self.type.get_c_name(), self.name, self.len)
        else:
            return f"{self.type.get_c_name()} {self.name};"

    def get_swap_to_be_code(self, struct, var):
        if self.len is not None and type(self.len) != dict:
            if self.len > 0:
                return (
                    "do { unsigned i; for (i = 0; i < %d; ++i) { %s } }"
                    " while(0);"
                    % (
                        self.len,
                        self.type.get_swap_to_be_code(struct, f"{var}[i]"),
                    )
                )

            nelem_field = (
                f"{self.nelem_field.type.get_swap_to_host_func_name()}({struct}{self.nelem_field.name})"
                if self.nelem_field.needs_byte_swap()
                else f"{struct}{self.nelem_field.name}"
            )

            return (
                "do { unsigned i; for (i = 0; i < %s; ++i) { %s } }"
                " while(0);"
                % (nelem_field, self.type.get_swap_to_be_code(struct, f"{var}[i]"))
            )

        return self.type.get_swap_to_be_code(struct, f"{var}")

    def get_swap_to_host_code(self, struct, var):
        if self.len is not None and type(self.len) != dict:
            if self.len > 0:
                return (
                    "do { unsigned i; for (i = 0; i < %d; ++i) { %s } }"
                    " while(0);"
                    % (
                        self.len,
                        self.type.get_swap_to_host_code(struct, f"{var}[i]"),
                    )
                )

            else:
                # nelem_field already swapped to host here...
                return (
                    "do { unsigned i; for (i = 0; i < %s%s; ++i) { %s } }"
                    " while(0);"
                    % (
                        struct,
                        self.nelem_field.name,
                        self.type.get_swap_to_host_code(struct, f"{var}[i]"),
                    )
                )

        return self.type.get_swap_to_host_code(struct, f"{var}")

    def needs_byte_swap(self):
        return self.type.needs_byte_swap()

    def get_vla_field_length_name(self, path):
        return f'{"_".join(path)}_{self.name}_array_size'

    def get_alloc_vla_param_names(self, path):
        result = [self.get_vla_field_length_name(path)] if self.is_vla() else []
        if self.type.has_vla():
            t = self.type.get_alloc_vla_param_names(path + [self.name])
            result.extend(t)
        return result

    def get_vla_calc_size_code(self, prefix, path):
        if self.is_vla():
            result = [
                f'sizeof({".".join([prefix] + path)}.{self.name}[0]) * {self.get_vla_field_length_name(path)}'
            ]

        else:
            result = []
        if self.type.has_vla():
            t = self.type.get_vla_calc_size_code(prefix, path + [self.name])
            result.extend(t)
        return result

    def get_vla_assign_code(self, prefix, path):
        result = []
        if self.is_vla():
            result.append(
                f'{".".join([prefix] + path)}.{self.nelem_field.name} = {self.get_vla_field_length_name(path)}'
            )

        if self.type.has_vla():
            t = self.type.get_vla_assign_code(prefix, path + [self.name])
            result.extend(t)
        return result


class CAlias(CField):
    def get_c_name(self):
        return f"vapi_type_{self.name}"

    def get_c_def(self):
        if self.len is not None:
            return "typedef %s vapi_type_%s[%d];" % (
                self.type.get_c_name(), self.name, self.len)
        else:
            return f"typedef {self.type.get_c_name()} vapi_type_{self.name};"


class CStruct(Struct):
    def get_c_def(self):
        return "\n".join(
            [
                (
                    "typedef struct __attribute__((__packed__)) {\n%s"
                    % "\n".join([f"  {x.get_c_def()}" for x in self.fields])
                ),
                "} %s;" % self.get_c_name(),
            ]
        )

    def get_vla_assign_code(self, prefix, path):
        return [x for f in self.fields if f.has_vla()
                for x in f.get_vla_assign_code(prefix, path)]

    def get_alloc_vla_param_names(self, path):
        return [x for f in self.fields
                if f.has_vla()
                for x in f.get_alloc_vla_param_names(path)]

    def get_vla_calc_size_code(self, prefix, path):
        return [x for f in self.fields if f.has_vla()
                for x in f.get_vla_calc_size_code(prefix, path)]


class CSimpleType (SimpleType):

    swap_to_be_dict = {
        'i16': 'htobe16', 'u16': 'htobe16',
        'i32': 'htobe32', 'u32': 'htobe32',
        'i64': 'htobe64', 'u64': 'htobe64',
    }

    swap_to_host_dict = {
        'i16': 'be16toh', 'u16': 'be16toh',
        'i32': 'be32toh', 'u32': 'be32toh',
        'i64': 'be64toh', 'u64': 'be64toh',
    }

    __packed = "__attribute__((packed))"
    pack_dict = {
        'i8':  __packed, 'u8':  __packed,
        'i16': __packed, 'u16': __packed,
    }

    def get_c_name(self):
        return self.name

    def get_swap_to_be_func_name(self):
        return self.swap_to_be_dict[self.name]

    def get_swap_to_host_func_name(self):
        return self.swap_to_host_dict[self.name]

    def get_packed_string(self):
        return self.pack_dict[self.name]

    def get_swap_to_be_code(self, struct, var, cast=None):
        x = f"{struct}{var}"
        return f'{x} = {f"({cast})" if cast else ""}{self.get_swap_to_be_func_name()}({x});'

    def get_swap_to_host_code(self, struct, var, cast=None):
        x = f"{struct}{var}"
        return f'{x} = {f"({cast})" if cast else ""}{self.get_swap_to_host_func_name()}({x});'

    def needs_byte_swap(self):
        try:
            self.get_swap_to_host_func_name()
            return True
        except KeyError:
            pass
        return False

    def get_packed(self):
        return self.pack_dict.get(self.name, "")


class CEnum(Enum):
    def get_c_name(self):
        return f"vapi_enum_{self.name}"

    def get_c_def(self):
        return "typedef enum {\n%s\n} %s %s;" % (
            "\n".join([f"  {i} = {j}," for i, j in self.value_pairs]),
            self.type.get_packed(),
            self.get_c_name(),
        )

    def needs_byte_swap(self):
        return self.type.needs_byte_swap()

    def get_swap_to_be_code(self, struct, var):
        return self.type.get_swap_to_be_code(struct, var, self.get_c_name())

    def get_swap_to_host_code(self, struct, var):
        return self.type.get_swap_to_host_code(struct, var, self.get_c_name())


class CUnion(Union):
    def get_c_name(self):
        return f"vapi_union_{self.name}"

    def get_c_def(self):
        return "typedef union {\n%s\n} %s;" % (
            "\n".join([f"  {i.get_c_name()} {j};" for i, j in self.type_pairs]),
            self.get_c_name(),
        )

    def needs_byte_swap(self):
        return False


class CStructType (StructType, CStruct):
    def get_c_name(self):
        return f"vapi_type_{self.name}"

    def get_swap_to_be_func_name(self):
        return f"{self.get_c_name()}_hton"

    def get_swap_to_host_func_name(self):
        return f"{self.get_c_name()}_ntoh"

    def get_swap_to_be_func_decl(self):
        return f"void {self.get_swap_to_be_func_name()}({self.get_c_name()} *msg)"

    def get_swap_to_be_func_def(self):
        return "%s\n{\n%s\n}" % (
            self.get_swap_to_be_func_decl(),
            "\n".join(
                [
                    f'  {p.get_swap_to_be_code("msg->", f"{p.name}")}'
                    for p in self.fields
                    if p.needs_byte_swap()
                ]
            ),
        )

    def get_swap_to_host_func_decl(self):
        return f"void {self.get_swap_to_host_func_name()}({self.get_c_name()} *msg)"

    def get_swap_to_host_func_def(self):
        return "%s\n{\n%s\n}" % (
            self.get_swap_to_host_func_decl(),
            "\n".join(
                [
                    f'  {p.get_swap_to_host_code("msg->", f"{p.name}")}'
                    for p in self.fields
                    if p.needs_byte_swap()
                ]
            ),
        )

    def get_swap_to_be_code(self, struct, var):
        return f"{self.get_swap_to_be_func_name()}(&{struct}{var});"

    def get_swap_to_host_code(self, struct, var):
        return f"{self.get_swap_to_host_func_name()}(&{struct}{var});"

    def needs_byte_swap(self):
        return any(f.needs_byte_swap() for f in self.fields)


class CMessage (Message):
    def __init__(self, logger, definition, json_parser):
        super(CMessage, self).__init__(logger, definition, json_parser)
        self.payload_members = [
            f"  {p.get_c_def()}" for p in self.fields if p.type != self.header
        ]

    def has_payload(self):
        return len(self.payload_members) > 0

    def get_msg_id_name(self):
        return f"vapi_msg_id_{self.name}"

    def get_c_name(self):
        return f"vapi_msg_{self.name}"

    def get_payload_struct_name(self):
        return f"vapi_payload_{self.name}"

    def get_alloc_func_name(self):
        return f"vapi_alloc_{self.name}"

    def get_alloc_vla_param_names(self):
        return [x for f in self.fields
                if f.has_vla()
                for x in f.get_alloc_vla_param_names([])]

    def get_alloc_func_decl(self):
        return "%s* %s(struct vapi_ctx_s *ctx%s)" % (
            self.get_c_name(),
            self.get_alloc_func_name(),
            "".join([f", size_t {n}" for n in self.get_alloc_vla_param_names()]),
        )

    def get_alloc_func_def(self):
        extra = []
        if self.header.has_field('client_index'):
            extra.append(
                "  msg->header.client_index = vapi_get_client_index(ctx);")
        if self.header.has_field('context'):
            extra.append("  msg->header.context = 0;")
        return "\n".join(
            (
                (
                    [
                        f"{self.get_alloc_func_decl()}",
                        "{",
                        f"  {self.get_c_name()} *msg = NULL;",
                        (
                            "  const size_t size = sizeof(%s)%s;"
                            % (
                                self.get_c_name(),
                                "".join(
                                    [
                                        f" + {x}"
                                        for f in self.fields
                                        if f.has_vla()
                                        for x in f.get_vla_calc_size_code(
                                            "msg->payload", []
                                        )
                                    ]
                                ),
                            )
                        ),
                        "  /* cast here required to play nicely with C++ world ... */",
                        f"  msg = ({self.get_c_name()}*)vapi_msg_alloc(ctx, size);",
                        "  if (!msg) {",
                        "    return NULL;",
                        "  }",
                    ]
                    + extra
                )
                + [
                    f"  msg->header._vl_msg_id = vapi_lookup_vl_msg_id(ctx, {self.get_msg_id_name()});",
                    "".join(
                        [
                            "  %s;\n" % line
                            for f in self.fields
                            if f.has_vla()
                            for line in f.get_vla_assign_code("msg->payload", [])
                        ]
                    ),
                    "  return msg;",
                    "}",
                ]
            )
        )

    def get_calc_msg_size_func_name(self):
        return f"vapi_calc_{self.name}_msg_size"

    def get_calc_msg_size_func_decl(self):
        return f"uword {self.get_calc_msg_size_func_name()}({self.get_c_name()} *msg)"

    def get_calc_msg_size_func_def(self):
        return "\n".join(
            [
                f"{self.get_calc_msg_size_func_decl()}",
                "{",
                (
                    "  return sizeof(*msg)%s;"
                    % "".join(
                        [
                            f"+ msg->payload.{f.nelem_field.name} * sizeof(msg->payload.{f.name}[0])"
                            for f in self.fields
                            if f.nelem_field is not None
                        ]
                    )
                ),
                "}",
            ]
        )

    def get_c_def(self):
        if self.has_payload():
            return "\n".join(
                [
                    "typedef struct __attribute__ ((__packed__)) {",
                    "%s " % "\n".join(self.payload_members),
                    "} %s;" % self.get_payload_struct_name(),
                    "",
                    "typedef struct __attribute__ ((__packed__)) {",
                    f"  {self.header.get_c_name()} {self.fields[0].name};"
                    if self.header is not None
                    else "",
                    f"  {self.get_payload_struct_name()} payload;",
                    "} %s;" % self.get_c_name(),
                ]
            )

        else:
            return "\n".join(
                [
                    "typedef struct __attribute__ ((__packed__)) {",
                    f"  {self.header.get_c_name()} {self.fields[0].name};"
                    if self.header is not None
                    else "",
                    "} %s;" % self.get_c_name(),
                ]
            )

    def get_swap_payload_to_host_func_name(self):
        return f"{self.get_c_name()}_payload_ntoh"

    def get_swap_payload_to_be_func_name(self):
        return f"{self.get_c_name()}_payload_hton"

    def get_swap_payload_to_host_func_decl(self):
        return f"void {self.get_swap_payload_to_host_func_name()}({self.get_payload_struct_name()} *payload)"

    def get_swap_payload_to_be_func_decl(self):
        return f"void {self.get_swap_payload_to_be_func_name()}({self.get_payload_struct_name()} *payload)"

    def get_swap_payload_to_be_func_def(self):
        return "%s\n{\n%s\n}" % (
            self.get_swap_payload_to_be_func_decl(),
            "\n".join(
                [
                    f'  {p.get_swap_to_be_code("payload->", f"{p.name}")}'
                    for p in self.fields
                    if p.needs_byte_swap() and p.type != self.header
                ]
            ),
        )

    def get_swap_payload_to_host_func_def(self):
        return "%s\n{\n%s\n}" % (
            self.get_swap_payload_to_host_func_decl(),
            "\n".join(
                [
                    f'  {p.get_swap_to_host_code("payload->", f"{p.name}")}'
                    for p in self.fields
                    if p.needs_byte_swap() and p.type != self.header
                ]
            ),
        )

    def get_swap_to_host_func_name(self):
        return f"{self.get_c_name()}_ntoh"

    def get_swap_to_be_func_name(self):
        return f"{self.get_c_name()}_hton"

    def get_swap_to_host_func_decl(self):
        return f"void {self.get_swap_to_host_func_name()}({self.get_c_name()} *msg)"

    def get_swap_to_be_func_decl(self):
        return f"void {self.get_swap_to_be_func_name()}({self.get_c_name()} *msg)"

    def get_swap_to_be_func_def(self):
        return "\n".join(
            [
                f"{self.get_swap_to_be_func_decl()}",
                "{",
                "  VAPI_DBG(\"Swapping `%s'@%%p to big endian\", msg);"
                % self.get_c_name(),
                f"  {self.header.get_swap_to_be_func_name()}(&msg->header);"
                if self.header is not None
                else "",
                f"  {self.get_swap_payload_to_be_func_name()}(&msg->payload);"
                if self.has_payload()
                else "",
                "}",
            ]
        )

    def get_swap_to_host_func_def(self):
        return "\n".join(
            [
                f"{self.get_swap_to_host_func_decl()}",
                "{",
                "  VAPI_DBG(\"Swapping `%s'@%%p to host byte order\", msg);"
                % self.get_c_name(),
                f"  {self.header.get_swap_to_host_func_name()}(&msg->header);"
                if self.header is not None
                else "",
                f"  {self.get_swap_payload_to_host_func_name()}(&msg->payload);"
                if self.has_payload()
                else "",
                "}",
            ]
        )

    def get_op_func_name(self):
        return f"vapi_{self.name}"

    def get_op_func_decl(self):
        if self.reply.has_payload():
            return "vapi_error_e %s(%s)" % (
                self.get_op_func_name(),
                ",\n  ".join(
                    [
                        'struct vapi_ctx_s *ctx',
                        f'{self.get_c_name()} *msg',
                        'vapi_error_e (*callback)(struct vapi_ctx_s *ctx',
                        '                         void *callback_ctx',
                        '                         vapi_error_e rv',
                        '                         bool is_last',
                        f'                         {self.reply.get_payload_struct_name()} *reply)',
                        'void *callback_ctx',
                    ]
                ),
            )

        else:
            return "vapi_error_e %s(%s)" % (
                self.get_op_func_name(),
                ",\n  ".join(
                    [
                        'struct vapi_ctx_s *ctx',
                        f'{self.get_c_name()} *msg',
                        'vapi_error_e (*callback)(struct vapi_ctx_s *ctx',
                        '                         void *callback_ctx',
                        '                         vapi_error_e rv',
                        '                         bool is_last)',
                        'void *callback_ctx',
                    ]
                ),
            )

    def get_op_func_def(self):
        return "\n".join(
            [
                f"{self.get_op_func_decl()}",
                "{",
                "  if (!msg || !callback) {",
                "    return VAPI_EINVAL;",
                "  }",
                "  if (vapi_is_nonblocking(ctx) && vapi_requests_full(ctx)) {",
                "    return VAPI_EAGAIN;",
                "  }",
                "  vapi_error_e rv;",
                "  if (VAPI_OK != (rv = vapi_producer_lock (ctx))) {",
                "    return rv;",
                "  }",
                "  u32 req_context = vapi_gen_req_context(ctx);",
                "  msg->header.context = req_context;",
                f"  {self.get_swap_to_be_func_name()}(msg);",
                "  if (VAPI_OK == (rv = vapi_send_with_control_ping "
                "(ctx, msg, req_context))) {"
                if self.reply_is_stream
                else "  if (VAPI_OK == (rv = vapi_send (ctx, msg))) {",
                "    vapi_store_request(ctx, req_context, %s, "
                "(vapi_cb_t)callback, callback_ctx);"
                % ("true" if self.reply_is_stream else "false"),
                "    if (VAPI_OK != vapi_producer_unlock (ctx)) {",
                "      abort (); /* this really shouldn't happen */",
                "    }",
                "    if (vapi_is_nonblocking(ctx)) {",
                "      rv = VAPI_OK;",
                "    } else {",
                "      rv = vapi_dispatch(ctx);",
                "    }",
                "  } else {",
                f"    {self.get_swap_to_host_func_name()}(msg);",
                "    if (VAPI_OK != vapi_producer_unlock (ctx)) {",
                "      abort (); /* this really shouldn't happen */",
                "    }",
                "  }",
                "  return rv;",
                "}",
                "",
            ]
        )

    def get_event_cb_func_decl(self):
        if not self.is_reply and not self.is_event:
            raise Exception(
                "Cannot register event callback for non-reply message")
        if self.has_payload():
            return "\n".join(
                [
                    f"void vapi_set_{self.get_c_name()}_event_cb (",
                    "  struct vapi_ctx_s *ctx, ",
                    "  vapi_error_e (*callback)(struct vapi_ctx_s *ctx, "
                    "void *callback_ctx, %s *payload),"
                    % self.get_payload_struct_name(),
                    "  void *callback_ctx)",
                ]
            )

        else:
            return "\n".join(
                [
                    f"void vapi_set_{self.get_c_name()}_event_cb (",
                    "  struct vapi_ctx_s *ctx, ",
                    "  vapi_error_e (*callback)(struct vapi_ctx_s *ctx, "
                    "void *callback_ctx),",
                    "  void *callback_ctx)",
                ]
            )

    def get_event_cb_func_def(self):
        if not self.is_reply and not self.is_event:
            raise Exception(
                "Cannot register event callback for non-reply function")
        return "\n".join(
            [
                f"{self.get_event_cb_func_decl()}",
                "{",
                "  vapi_set_event_cb(ctx, %s, (vapi_event_cb)callback, "
                "callback_ctx);" % self.get_msg_id_name(),
                "}",
            ]
        )

    def get_c_metadata_struct_name(self):
        return f"__vapi_metadata_{self.name}"

    def get_c_constructor(self):
        has_context = False
        if self.header is not None:
            has_context = self.header.has_field('context')
        return '\n'.join(
            [
                f'static void __attribute__((constructor)) __vapi_constructor_{self.name}()',
                '{',
                '  static const char name[] = "%s";' % self.name,
                '  static const char name_with_crc[] = "%s_%s";'
                % (self.name, self.crc[2:]),
                '  static vapi_message_desc_t %s = {'
                % self.get_c_metadata_struct_name(),
                '    name,',
                '    sizeof(name) - 1,',
                '    name_with_crc,',
                '    sizeof(name_with_crc) - 1,',
                '    true,' if has_context else '    false,',
                f'    offsetof({self.header.get_c_name()}, context),'
                if has_context
                else '    0,',
                f'    offsetof({self.get_c_name()}, payload),'
                if self.has_payload()
                else '    VAPI_INVALID_MSG_ID,',
                f'    sizeof({self.get_c_name()}),',
                f'    (generic_swap_fn_t){self.get_swap_to_be_func_name()},',
                f'    (generic_swap_fn_t){self.get_swap_to_host_func_name()},',
                '    VAPI_INVALID_MSG_ID,',
                '  };',
                '',
                f'  {self.get_msg_id_name()} = vapi_register_msg(&{self.get_c_metadata_struct_name()});',
                '  VAPI_DBG("Assigned msg id %%d to %s", %s);'
                % (self.name, self.get_msg_id_name()),
                '}',
            ]
        )


vapi_send_with_control_ping = """
static inline vapi_error_e
vapi_send_with_control_ping (vapi_ctx_t ctx, void *msg, u32 context)
{
  vapi_msg_control_ping *ping = vapi_alloc_control_ping (ctx);
  if (!ping)
    {
      return VAPI_ENOMEM;
    }
  ping->header.context = context;
  vapi_msg_control_ping_hton (ping);
  return vapi_send2 (ctx, msg, ping);
}
"""


def emit_definition(parser, json_file, emitted, o):
    if o in emitted:
        return
    if o.name in ("msg_header1_t", "msg_header2_t"):
        return
    if hasattr(o, "depends"):
        for x in o.depends:
            emit_definition(parser, json_file, emitted, x)
    if hasattr(o, "reply"):
        emit_definition(parser, json_file, emitted, o.reply)
    if hasattr(o, "get_c_def"):
        if (o not in parser.enums_by_json[json_file] and
                o not in parser.types_by_json[json_file] and
                o not in parser.unions_by_json[json_file] and
                o.name not in parser.messages_by_json[json_file] and
                o not in parser.aliases_by_json[json_file]):
            return
        guard = f"defined_{o.get_c_name()}"
        print(f"#ifndef {guard}")
        print(f"#define {guard}")
        print(f"{o.get_c_def()}")
        print("")
        function_attrs = "static inline "
        if o.name in parser.messages_by_json[json_file]:
            if o.has_payload():
                print(f"{function_attrs}{o.get_swap_payload_to_be_func_def()}")
                print("")
                print(f"{function_attrs}{o.get_swap_payload_to_host_func_def()}")
                print("")
            print(f"{function_attrs}{o.get_swap_to_be_func_def()}")
            print("")
            print(f"{function_attrs}{o.get_swap_to_host_func_def()}")
            print("")
            print(f"{function_attrs}{o.get_calc_msg_size_func_def()}")
            if not o.is_reply and not o.is_event:
                print("")
                print(f"{function_attrs}{o.get_alloc_func_def()}")
                print("")
                print(f"{function_attrs}{o.get_op_func_def()}")
            print("")
            print(f"{o.get_c_constructor()}")
            if o.is_reply or o.is_event:
                print("")
                print(f"{function_attrs}{o.get_event_cb_func_def()};")
        elif hasattr(o, "get_swap_to_be_func_def"):
            print(f"{function_attrs}{o.get_swap_to_be_func_def()}")
            print("")
            print(f"{function_attrs}{o.get_swap_to_host_func_def()}")
        print("#endif")
        print("")
    emitted.append(o)


def gen_json_unified_header(parser, logger, j, io, name):
    d, f = os.path.split(j)
    logger.info("Generating header `%s'" % name)
    orig_stdout = sys.stdout
    sys.stdout = io
    include_guard = "__included_%s" % (
        j.replace(".", "_").replace("/", "_").replace("-", "_").replace("+", "_"))
    print(f"#ifndef {include_guard}")
    print(f"#define {include_guard}")
    print("")
    print("#include <stdlib.h>")
    print("#include <stddef.h>")
    print("#include <arpa/inet.h>")
    print("#include <vapi/vapi_internal.h>")
    print("#include <vapi/vapi.h>")
    print("#include <vapi/vapi_dbg.h>")
    print("")
    print("#ifdef __cplusplus")
    print("extern \"C\" {")
    print("#endif")
    if name == "vpe.api.vapi.h":
        print("")
        print("static inline vapi_error_e vapi_send_with_control_ping "
              "(vapi_ctx_t ctx, void * msg, u32 context);")
    else:
        print("#include <vapi/vpe.api.vapi.h>")
    print("")
    for m in parser.messages_by_json[j].values():
        print(f"extern vapi_msg_id_t {m.get_msg_id_name()};")
    print("")
    print("#define DEFINE_VAPI_MSG_IDS_%s\\" %
          f.replace(".", "_").replace("/", "_").replace("-", "_").upper())
    print(
        "\\\n".join(
            [
                f"  vapi_msg_id_t {m.get_msg_id_name()};"
                for m in parser.messages_by_json[j].values()
            ]
        )
    )

    print("")
    print("")
    emitted = []
    for e in parser.enums_by_json[j]:
        emit_definition(parser, j, emitted, e)
    for u in parser.unions_by_json[j]:
        emit_definition(parser, j, emitted, u)
    for t in parser.types_by_json[j]:
        emit_definition(parser, j, emitted, t)
    for a in parser.aliases_by_json[j]:
        emit_definition(parser, j, emitted, a)
    for m in parser.messages_by_json[j].values():
        emit_definition(parser, j, emitted, m)

    print("")

    if name == "vpe.api.vapi.h":
        print(f"{vapi_send_with_control_ping}")
        print("")

    print("#ifdef __cplusplus")
    print("}")
    print("#endif")
    print("")
    print("#endif")
    sys.stdout = orig_stdout


def json_to_c_header_name(json_name):
    if json_name.endswith(".json"):
        return f"{os.path.splitext(json_name)[0]}.vapi.h"
    raise Exception("Unexpected json name `%s'!" % json_name)


def gen_c_unified_headers(parser, logger, prefix, remove_path):
    prefix = "" if prefix == "" or prefix is None else f"{prefix}/"
    for j in parser.json_files:
        if remove_path:
            d, f = os.path.split(j)
        else:
            f = j
        with open(f'{prefix}{json_to_c_header_name(f)}', "w") as io:
            gen_json_unified_header(
                parser, logger, j, io, json_to_c_header_name(f))


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
    logger = logging.getLogger("VAPI C GEN")
    logger.setLevel(log_level)

    argparser = argparse.ArgumentParser(description="VPP C API generator")
    argparser.add_argument('files', metavar='api-file', action='append',
                           type=str, help='json api file'
                           '(may be specified multiple times)')
    argparser.add_argument('--prefix', action='store', default=None,
                           help='path prefix')
    argparser.add_argument('--remove-path', action='store_true',
                           help='remove path from filename')
    args = argparser.parse_args()

    jsonparser = JsonParser(logger, args.files,
                            simple_type_class=CSimpleType,
                            enum_class=CEnum,
                            union_class=CUnion,
                            struct_type_class=CStructType,
                            field_class=CField,
                            message_class=CMessage,
                            alias_class=CAlias)

    # not using the model of having separate generated header and code files
    # with generated symbols present in shared library (per discussion with
    # Damjan), to avoid symbol version issues in .so
    # gen_c_headers_and_code(jsonparser, logger, args.prefix)

    gen_c_unified_headers(jsonparser, logger, args.prefix, args.remove_path)

    for e in jsonparser.exceptions:
        logger.warning(e)
