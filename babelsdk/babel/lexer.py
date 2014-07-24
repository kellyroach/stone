import logging
import ply.lex as lex

class MultiToken(object):
    """Object used to monkeypatch ply.lex so that we can return multiple
    tokens from one lex operation."""
    def __init__(self, tokens):
        self.type = tokens[0].type
        self.tokens = tokens

class BabelLexer(object):
    """
    Lexer.
    """

    def __init__(self):
        self.lex = None
        self.tokens_queue = None
        self.cur_indent = None
        self._logger = logging.getLogger('babelsdk.babel.lexer')
        self.last_token = None

    def input(self, file_data, **kwargs):
        """
        Required by ply.yacc for this to quack (duck typing) like a ply lexer.

        :param str file_data: Contents of the file to lex.
        """
        self.lex = lex.lex(module=self, **kwargs)
        self.tokens_queue = []
        self.cur_indent = 0
        # Hack to avoid tokenization bugs caused by files that do not end in a
        # new line.
        self.lex.input(file_data + '\n')

    def token(self):
        """
        Returns the next LexToken. Returns None when all tokens have been
        exhausted.
        """

        if self.tokens_queue:
            self.last_token = self.tokens_queue.pop(0)
        else:
            r = self.lex.token()
            if isinstance(r, MultiToken):
                self.tokens_queue.extend(r.tokens)
                self.last_token = self.tokens_queue.pop(0)
            else:
                if r is None and self.cur_indent > 0:
                    if self.last_token and self.last_token.type not in ('NEWLINE', 'LINE'):
                        newline_token = self._create_token('NEWLINE', '\n', self.lex.lineno, self.lex.lexpos)
                        self.tokens_queue.append(newline_token)
                    dedent_count = self.cur_indent / 4
                    dedent_token = self._create_token('DEDENT', '\t', self.lex.lineno, self.lex.lexpos)
                    self.tokens_queue.extend([dedent_token] * dedent_count)

                    self.cur_indent = 0
                    self.last_token = self.tokens_queue.pop(0)
                else:
                    self.last_token = r
        return self.last_token

    def _create_token(self, token_type, value, lineno, lexpos):
        """
        Helper for creating ply.lex.LexToken objects. Unfortunately, LexToken
        does not have a constructor defined to make settings these values easy.
        """
        token = lex.LexToken()
        token.type = token_type
        token.value = value
        token.lineno = lineno
        token.lexpos = lexpos
        return token

    def test(self, data):
        """Logs all tokens for human inspection. Useful for debugging."""
        self.input(data)
        while True:
            token = self.token()
            if not token:
                break
            self._logger.debug('Token %r', token)

    states = (
        # For switching to free text mode for doc strings.
        ('freetext', 'exclusive'),
    )

    # List of token names
    tokens = (
       'COLON',
       'ID',
       'KEYWORD',
       'PATH',
    )

    # Tokens related to free text
    tokens += (
       'DOUBLE_COLON',
       'LINE',
    )

    # Whitespace tokens
    tokens += (
        'DEDENT',
        'INDENT',
        'NEWLINE',
    )

    # Attribute lists, aliases
    tokens += (
        'COMMA',
        'EQ',
        'LPAR',
        'RPAR',
    )

    # Primitive types
    tokens += (
        'BOOLEAN',
        'FLOAT',
        'INTEGER',
        'NULL',
        'STRING',
    )

    # Regular expression rules for simple tokens
    t_LPAR  = r'\('
    t_RPAR  = r'\)'
    t_EQ = r'='
    t_COMMA = r','
    t_COLON = r':'

    KEYWORDS = [
        'alias',
        'doc',
        'example',
        'extends',
        'extras',
        'include',
        'namespace',
        'nullable',
        'op',
        'struct',
        'union',
        'request',
        'response',
        'error',
    ]

    RESERVED = {
        'error': 'ERROR',
        'extras': 'EXTRAS',
        'include': 'INCLUDE',
        'op': 'OP',
        'request': 'REQUEST',
        'response': 'RESPONSE',
    }

    tokens += tuple(RESERVED.values())

    def t_BOOLEAN(self, token):
        r'\btrue\b|\bfalse\b'
        token.value = bool(token.value)
        return token

    def t_NULL(self, token):
        r'\bnull\b'
        token.value = None
        return token

    # No leading digits
    def t_ID(self, token):
        r'[a-zA-Z_][a-zA-Z0-9_-]*'
        if token.value in self.KEYWORDS:
            token.type = self.RESERVED.get(token.value, 'KEYWORD')
            return token
        else:
            return token

    def t_PATH(self, token):
        r'\/[/a-zA-Z0-9_-]*'
        return token

    def t_DOUBLE_COLON(self, token):
        r'::'
        self._logger.debug('Pushing freetext stat')
        token.lexer.push_state('freetext')
        self.cur_indent += 4
        # TODO: Can we not force it? Should we emit an indent and newline token?
        return token

    def t_freetext_LINE(self, line_token):
        r'.*?\n'

        line_token.lexer.lineno += line_token.value.count("\n")
        tokens = [line_token]

        next_line_pos = line_token.lexpos + len(line_token.value)
        if next_line_pos == len(line_token.lexer.lexdata):
            return line_token

        line = line_token.lexer.lexdata[next_line_pos:].splitlines()[0]
        if not line:
            # Ignore blank lines
            return line_token

        indent = len(line) - len(line.lstrip())
        indent_spaces = indent - self.cur_indent
        if indent_spaces % 4 > 0:
            raise Exception('Indent was not divisible by 4.')

        indent_delta = indent_spaces / 4
        if indent_delta >= 0:
            # Ignore additional indents when in a freetext block.
            return line_token

        dedent_token = self._create_token('DEDENT', '\t', line_token.lineno + 1, next_line_pos)
        tokens.extend([dedent_token] * abs(indent_delta))
        line_token.lexer.pop_state()
        self.cur_indent = indent

        return MultiToken(tokens)

    t_freetext_ignore = ' \t'

    def t_FLOAT(self, token):
        r'((\d*\.\d+)(E[\+-]?\d+)?|([1-9]\d*E[\+-]?\d+))'
        token.value = float(token.value)
        return token

    def t_INTEGER(self, token):
        r'\d+'
        token.value = int(token.value)
        return token

    # Read in a string while respecting the following escape sequences:
    # \", \\, \n, and \t.
    def t_STRING(self, t):
        r'\"([^\\"]|(\\.))*\"'
        escaped = 0
        str = t.value[1:-1]
        new_str = ""
        for i in range(0, len(str)):
            c = str[i]
            if escaped:
                if c == 'n':
                    c = '\n'
                elif c == 't':
                    c = '\t'
                new_str += c
                escaped = 0
            else:
                if c == '\\':
                    escaped = 1
                else:
                    new_str += c
        t.value = new_str
        return t

    # Ignore comments.
    def t_comment(self, token):
        r'[#][^\n]*\n+'
        token.lexer.lineno += token.value.count('\n')

    # Define a rule so we can track line numbers
    def t_NEWLINE(self, newline_token):
        r'\n+'

        # Count lines
        newline_token.lexer.lineno += newline_token.value.count('\n')

        tokens = [newline_token]

        next_line_pos = newline_token.lexpos + len(newline_token.value)
        if next_line_pos == len(newline_token.lexer.lexdata):
            # Reached end of file
            return newline_token

        line = newline_token.lexer.lexdata[next_line_pos:].splitlines()[0]
        if not line:
            return newline_token

        indent = len(line) - len(line.lstrip())
        indent_spaces = indent - self.cur_indent
        if indent_spaces % 4 > 0:
            raise Exception('Indent was not divisible by 4.')

        indent_delta = indent_spaces / 4
        dent_type = 'INDENT' if indent_delta > 0 else 'DEDENT'
        dent_token = self._create_token(dent_type, '\t', newline_token.lineno + 1, next_line_pos)

        tokens.extend([dent_token] * abs(indent_delta))
        self.cur_indent = indent

        return MultiToken(tokens)

    # A string containing ignored characters (spaces and tabs)
    t_ignore = ' \t'

    # Error handling rule
    def t_error(self, token):
        self._logger.error('Illegal character %r at line %d', token.value[0], token.lexer.lineno)
        token.lexer.skip(1)

    # Use the same error handler in freetext mode
    t_freetext_error = t_error