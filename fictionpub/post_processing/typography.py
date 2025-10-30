import re
from lxml import etree

# --- Constants ---
DASHES = ('—', '–', '-')
# Regex to find any trailing punctuation, including dashes
PUNCTUATION_RE = re.compile(r'([.,:;?!' + "".join(DASHES) + r']+)$')

# TODO: apply NBSP and .nobreak inside sentences, not just at the start/end of <p>
# Start of <p> is guaranteed to begin at a new line, nbsp is not needed there. 
# But each sentence inside of a <p> needs the same processing.

def improve_typography(body: etree._Element, len_nbsp_range, len_nobreak_range):
    """
    Applies typographic tweaks to an XHTML body to improve word wrapping and hyphenation.

    This function performs two main operations on <p> tags with 2 or more words:
    1. Inserts a non-breaking space (&nbsp;) after first / before last words within a
       defined length range to prevent them from being orphaned. 
       This only happens if a regular space is present to be replaced.
    2. Wraps first/last words within a defined length range in <span class="nobreak">
       to suggest they not be hyphenated. The associated CSS should define this class,
       e.g., .nobreak { white-space: nowrap; }

    Args:
        body (etree._Element): The input XHTML content.

    Returns:
        bytes: The processed XHTML content as a UTF-8 encoded byte string.
    """
    # --- Configuration for typographic rules ---
    # Tuple format: (min_len, max_len). Applied to both first and last words.
    # 1. Insert NBSP if word length is within this range.
    # word_length_nbsp = (1, 2)
    # 2. Wrap word in no-break span if length is within this range.
    # word_length_nobreak = (4, 7)

    for p in body.iterfind(".//p"):
        # Join all text nodes and split by whitespace to get a word count
        all_text = " ".join(p.itertext()) # type: ignore
        words = all_text.split()
        
        # Skip paragraphs with fewer than 2 words
        if len(words) < 2:
            continue

        # Process the last word first, then the first. This order is generally more
        # robust as modifying the start of the paragraph's content can be more
        # disruptive to subsequent searches within the same paragraph element.
        _process_last_word(p, len_nbsp_range, len_nobreak_range)
        _process_first_word(p, len_nbsp_range, len_nobreak_range)


def _separate_punctuation(word_with_punct):
    """
    Separates a word from its trailing punctuation.
    
    Returns:
        (str, str): A tuple of (word, punctuation)
    """
    punct_match = PUNCTUATION_RE.search(word_with_punct)
    if punct_match:
        first_word = word_with_punct[:punct_match.start()]
        punctuation = punct_match.group(1)
    else:
        first_word = word_with_punct
        punctuation = ''
    return first_word, punctuation


def _find_first_text_owner(element):
    """
    Finds the element that "owns" the first piece of text content within a given element.
    Returns the owner element and whether the text is in its .text or .tail property.
    
    This function is recursive to ensure correct document text order.
    """
    # Text order: element.text, then children (recursively), then element.tail
    if element.text and element.text.strip():
        return element, 'text'

    for child in element: # Iterate over direct children
        # Recurse to find text in children and their descendants
        descendant_owner, descendant_attr = _find_first_text_owner(child)
        if descendant_owner is not None:
            return descendant_owner, descendant_attr
            
        # If no descendants had text, *now* check the child's tail
        if child.tail and child.tail.strip():
            return child, 'tail'
            
    return None, '' # No text found


def _find_last_text_owner(element):
    """
    Finds the element that "owns" the last piece of text content within a given element.
    This iterates in reverse document order to find the last text node.
    Returns the owner element and whether the text is in its .text or .tail property.
    """
    # A reversed list of the element and all its descendants gives us reverse document order.
    nodes_in_reverse = list(element.iter())
    nodes_in_reverse.reverse()

    # FIX: Find the last text node that contains an actual word character (\w).
    # This prevents stopping on nodes that only contain punctuation (e.g. "..." or "?").
    for node in nodes_in_reverse:
        if node is not element and node.tail and re.search(r'\w', node.tail):
            return node, 'tail'
        if node.text and re.search(r'\w', node.text):
            return node, 'text'
            
    # Fallback: If no node with a word is found (e.g., paragraph is just "."),
    # return the last text node anyway.
    for node in nodes_in_reverse:
        if node is not element and node.tail and node.tail.strip():
            return node, 'tail'
        if node.text and node.text.strip():
            return node, 'text'
            
    return None, ''


def _find_preceding_separator_owner(owner, attr):
    """
    Finds the node and attribute that contains the separator *before* the given node.
    This is used when the last word is in its own node (e.g., <strong>end</strong>)
    and the preceding space is in a different node.

    Returns: (separator_owner, separator_attr) or (None, None)
    """
    # Case 1: Word is in a .tail (e.g., <em>...</em> C).
    # Separator could be in owner's .text.
    if attr == 'tail':
        if owner.text and owner.text.rstrip() != owner.text:
            return owner, 'text'

    # Case 2: Word is in .text OR .tail.
    # Separator could be in previous sibling's .tail.
    prev_sibling = owner.getprevious()
    if prev_sibling is not None:
        if prev_sibling.tail and prev_sibling.tail.rstrip() != prev_sibling.tail:
            return prev_sibling, 'tail'
        # If prev_sibling has no tail, check its .text
        elif prev_sibling.tail is None and prev_sibling.text and prev_sibling.text.rstrip() != prev_sibling.text:
             return prev_sibling, 'text'

    # Case 3: Word is in .text OR .tail, and is the first child (or no prev sibling).
    # Separator could be in the parent's .text.
    if prev_sibling is None:
        parent = owner.getparent()
        if parent is not None and parent.text and parent.text.rstrip() != parent.text:
            return parent, 'text'
            
    return None, ''


def _find_first_node_with_leading_space(element):
    """
    Recursively finds the first descendant text node (.text or .tail)
    within 'element' that has leading whitespace.
    """
    # Check children
    for child in element:
        # Check child's text
        if child.text and child.text.lstrip() != child.text:
            return child, 'text'
        
        # Recurse into child
        owner, attr = _find_first_node_with_leading_space(child)
        if owner is not None: return owner, attr
        
        # Check child's tail
        if child.tail and child.tail.lstrip() != child.tail:
            return child, 'tail'
    return None, ''


def _find_next_separator_owner(owner, attr):
    """
    Finds the next text node that has leading whitespace, starting
    after the node specified by (owner, attr).
    """
    if attr == 'text':
        # 1. Check owner's children
        child_owner, child_attr = _find_first_node_with_leading_space(owner)
        if child_owner is not None: return child_owner, child_attr

        # 2. Check owner's tail
        if owner.tail and owner.tail.lstrip() != owner.tail:
            return owner, 'tail'
        
        # 3. If no separator in children/tail, go up to parent and check siblings
        return _find_next_separator_owner_recursive_up(owner)
        
    if attr == 'tail':
        # 1. Go up to parent and check siblings/parent's tail
        return _find_next_separator_owner_recursive_up(owner)
        
    return None, ''


def _find_next_separator_owner_recursive_up(element):
    """
    Helper for _find_next_separator_owner.
    Recursively searches up and across siblings for a text node with leading space.
    """
    parent = element.getparent()
    if parent is None or parent.tag == 'p': # Stop at <p>
        return None, ''
        
    # Check next siblings
    next_sibling = element.next_sibling
    while next_sibling is not None:
        # Check sibling's text
        if next_sibling.text and next_sibling.text.lstrip() != next_sibling.text:
            return next_sibling, 'text'
        
        # Check sibling's children
        child_owner, child_attr = _find_first_node_with_leading_space(next_sibling)
        if child_owner is not None: return child_owner, child_attr
        
        # Check sibling's tail
        if next_sibling.tail and next_sibling.tail.lstrip() != next_sibling.tail:
            return next_sibling, 'tail'
            
        next_sibling = next_sibling.next_sibling
        
    # If no next siblings have it, check parent's tail
    if parent.tail and parent.tail.lstrip() != parent.tail:
        return parent, 'tail'
        
    # If not, recurse up
    return _find_next_separator_owner_recursive_up(parent)


def _process_first_word(p, len_nbsp_range, len_nobreak_range):
    """Processes the first word of a paragraph."""
    # TODO: The very first word of a <p> needs no proсessing, skip it.
    owner, attr = _find_first_text_owner(p)
    if owner is None: return

    original_text = getattr(owner, attr)
    stripped_text = original_text.lstrip()
    leading_ws = original_text[:-len(stripped_text)]

    # Find the first word and the separator that follows it.
    # The separator might be in this text node, or in the element's tail.
    match = re.search(r'\s', stripped_text)
    
    separator_node_owner = None
    
    if match: # Case A: Word and separator are in the same text node.
        first_word_with_punct = stripped_text[:match.start()]
        separator = match.group(0)
        rest_of_text = stripped_text[match.end():]
        separator_node_owner = owner # Separator is in the same node
        separator_attr = attr       #
    else: # Case B: Word is at the end of this node. Find separator elsewhere.
        first_word_with_punct = stripped_text
        
        # FIX: Recursively search for the next text node with leading space
        separator_node_owner, separator_attr = _find_next_separator_owner(owner, attr)
        
        if separator_node_owner is not None:
            # Found the separator node
            sep_text = getattr(separator_node_owner, separator_attr)
            lstripped_sep_text = sep_text.lstrip()
            separator = sep_text[:-len(lstripped_sep_text)]
            rest_of_text = lstripped_sep_text
        else: # Case C: No separator found anywhere.
            separator = ''
            rest_of_text = ''

    # --- Refactored Part ---
    # Separate word from any trailing punctuation
    first_word, punctuation = _separate_punctuation(first_word_with_punct)
    
    word_len = len(first_word)
    if word_len == 0: return

    needs_nobreak = len_nobreak_range[0] <= word_len <= len_nobreak_range[1]
    needs_nbsp = len_nbsp_range[0] <= word_len <= len_nbsp_range[1]

    # Only proceed if an action is needed AND a separator exists for nbsp.
    # The separator must contain a space (e.g., " " or " \n")
    if not needs_nobreak and not (needs_nbsp and ' ' in separator):
        return
    
    new_separator = separator
    if needs_nbsp and ' ' in separator:
        # FIX (Case 11): Check if separator contains a dash
        is_dash_separator = any(dash in separator for dash in DASHES)
        
        # Do not add nbsp after dashes (e.g. "state-of-the-art ")
        # AND do not add nbsp before dashes (e.g. "Go — now")
        if not first_word_with_punct.rstrip().endswith(DASHES) and not is_dash_separator:
            # FIX: Do not add nbsp if word is followed by punctuation (Case 9)
            if not punctuation:
                new_separator = separator.replace(' ', '\u00A0', 1)
        
    # Apply modifications
    if needs_nobreak:
        span = etree.Element('span')
        span.set('class', 'nobreak')
        span.text = first_word

        # The original text node is now just the leading whitespace
        setattr(owner, attr, leading_ws)
        
        # Insert the new span
        if attr == 'text':
            owner.insert(0, span)
        else:  # attr == 'tail'
            parent = owner.getparent()
            parent.insert(parent.index(owner) + 1, span)
            
        # Put the rest of the text after the span
        if separator_node_owner is not None and (separator_node_owner != owner or separator_attr != attr):
            # Case B: Separator was in a *different* node (e.g., tail or sibling)
            span.tail = punctuation # Punctuation goes right after the word
            setattr(separator_node_owner, separator_attr, new_separator + rest_of_text)
        else: 
            # Case A: Separator was in the same node
            span.tail = punctuation + new_separator + rest_of_text

    elif new_separator != separator:  # Only needs NBSP, no nobreak
        if separator_node_owner is not None and (separator_node_owner != owner or separator_attr != attr):
            # Case B: modify the *different* node
            setattr(separator_node_owner, separator_attr, new_separator + rest_of_text)
        else: 
            # Case A: modify the original text node
            new_text = f"{leading_ws}{first_word_with_punct}{new_separator}{rest_of_text}"
            setattr(owner, attr, new_text)


def _process_last_word(p, len_nbsp_range, len_nobreak_range):
    """Processes the last word of a paragraph."""
    owner, attr = _find_last_text_owner(p)
    if owner is None: return

    text_to_process = getattr(owner, attr)
    attr_to_modify = attr

    # If the last node is a tail with only punctuation, and the owner tag
    # itself has text, then process the tag's text and append the tail's content.
    if attr == 'tail' and not re.search(r'\w', text_to_process) and owner.text and owner.text.strip():
        punctuation_from_tail = text_to_process
        text_to_process = owner.text + punctuation_from_tail
        attr_to_modify = 'text'
        owner.tail = None
    
    original_text = text_to_process
    lstripped_text = original_text.lstrip()
    leading_ws = original_text[:-len(lstripped_text)]
    rstripped_text = lstripped_text.rstrip()
    trailing_ws = lstripped_text[len(rstripped_text):]
    stripped_text = rstripped_text

    matches = list(re.finditer(r'\s', stripped_text))
    
    sep_owner, sep_attr = None, ''
    sep_text_before = ""
    separator = ""
    
    if not matches: # Word is standalone in this node
        last_word_with_punct = stripped_text
        text_before_word = ""
        
        # Check for separator *inside* this node's leading whitespace
        if ' ' in leading_ws:
            sep_owner, sep_attr = owner, attr_to_modify
            separator = leading_ws
            sep_text_before = ""
        else:
            # Check for separator in a *preceding* text node
            sep_owner, sep_attr = _find_preceding_separator_owner(owner, attr)
            if sep_owner is not None:
                sep_text = getattr(sep_owner, sep_attr)
                rstripped_sep_text = sep_text.rstrip()
                separator = sep_text[len(rstripped_sep_text):]
                sep_text_before = rstripped_sep_text
            else:
                separator = "" # No separator found
    else:
        # Separator is inside this text node
        sep_owner, sep_attr = owner, attr_to_modify
        last_match = matches[-1]
        last_word_with_punct = stripped_text[last_match.end():]
        separator = last_match.group(0)
        text_before_word = stripped_text[:last_match.start()]
        sep_text_before = leading_ws + text_before_word
        
    # --- Refactored Part ---
    # Separate word from any trailing punctuation
    last_word, punctuation = _separate_punctuation(last_word_with_punct)

    word_len = len(last_word)
    if word_len == 0: return
    
    needs_nobreak = len_nobreak_range[0] <= word_len <= len_nobreak_range[1]
    needs_nbsp = len_nbsp_range[0] <= word_len <= len_nbsp_range[1] # <-- FIX: Was len_nobreak_range[1]

    # Only proceed if action is needed and separator exists
    if not needs_nobreak and not (needs_nbsp and ' ' in separator):
        return

    new_separator = separator
    if needs_nbsp and ' ' in separator:
        # Do not add nbsp after dashes (e.g. "Go — now")
        if not text_before_word.rstrip().endswith(DASHES):
            new_separator = separator.replace(' ', '\u00A0', 1)

    if needs_nobreak:
        span = etree.Element('span')
        span.set('class', 'nobreak')
        span.text = last_word
        span.tail = punctuation + trailing_ws
        
        # 1. Set the text of the separator node
        if sep_owner is not None:
            setattr(sep_owner, sep_attr, sep_text_before + new_separator)
        
        # 2. Clear the word from its original node (if it's different from separator node)
        if sep_owner != owner or sep_attr != attr_to_modify:
            if not matches: # Word was standalone in its node
                setattr(owner, attr_to_modify, leading_ws) # Clear the word, keep leading ws
            else:
                # This branch implies separator and word are in the same node,
                # which contradicts the outer 'if'. Should not be hit.
                pass
        
        # 3. Insert the span
        # FIX: Check the *original* attribute to decide where to insert
        if attr_to_modify == 'text':
            owner.append(span) # Append to the word's *original* owner
        else: # attr_to_modify == 'tail'
            parent = owner.getparent()
            parent.insert(parent.index(owner) + 1, span) # Insert after the word's *original* owner

    elif new_separator != separator:  # Only needs NBSP
        # FIX: This block handles NBSP-only logic.
        
        if sep_owner == owner and sep_attr == attr_to_modify:
             # Separator and word are in the same node. Rebuild it.
             setattr(sep_owner, sep_attr, sep_text_before + new_separator + last_word_with_punct + trailing_ws)
        elif sep_owner is not None:
             # FIX (Case 8): Separator is in a different node.
             # Just change the separator node.
             # The word's node (owner) is left completely untouched.
             setattr(sep_owner, sep_attr, sep_text_before + new_separator)


# --- Example Usage ---
if __name__ == '__main__':
    xhtml_string = """<?xml version="1.0" encoding="UTF-8"?>
    <html>
    <head>
        <title>Test Document</title>
        <style>.nobreak { white-space: nowrap; }</style>
    </head>
    <body>
        <h1>Sample Cases</h1>
        <!-- Case 1: Short first word (A), long last word -->
        <p>A simple sentence for testing.</p>
        
        <!-- Case 2: Short first word (I), last word needs no-break -->
        <p>I am in <em>great</em> need of a test.</p>
        
        <!-- Case 3: First word inside a tag, last word needs no-break -->
        <p><em>Go</em> now, before it is too late!</p>
        
        <!-- Case 4: No short words -->
        <p>This paragraph has no short words at the edges.</p>
        
        <!-- Case 5: Single short word (SKIPPED) -->
        <p> A </p>
        
        <!-- Case 6: Mixed content (A <em>B</em> C) -->
        <p>A <em>B</em> C</p>
        
        <!-- Case 7: Empty paragraph (SKIPPED) -->
        <p>  </p>
        
        <!-- Case 8: Last word inside a tag (This is the <strong>end</strong>) -->
        <p>This is the <strong>ends</strong></p>

        <!-- Case 9: Punctuation attached to words -->
        <p>Go, now, before it is too late!</p>

        <!-- Case 10: Hyphenated words -->
        <p>A state-of-the-art machine is what we need.</p>
        
        <!-- Case 11: Em-dash and other tags -->
        <p>Go — <em>I beg you</em> — w!</p>
        
        <!-- Case 12: Existing non-breaking space (should not be altered) -->
        <p>I\u00A0 am here.</p>

        <!-- Case 13-->
        <p>The text ends with <a>a link</a>.</p>
        
        <!-- Case 14 -->
        <p><em><strong>A</strong> new</em> text ends with <a>a nested <b>b!</b>?</a>...</p>
    </body>
    </html>
    """
    
    xhtml_string = xhtml_string.encode('utf-8')
    parser = etree.HTMLParser(recover=False, remove_blank_text=False)
    tree = etree.fromstring(xhtml_string, parser)
    
    body = tree.find('.//body')
    if body is None:
        # If no <body> is found, process the entire document fragment.
        body = tree

    word_length_nbsp = (1, 2)
    word_length_nobreak = (4, 7)

    improve_typography(body, word_length_nbsp, word_length_nobreak)

    # Do not use pretty_print, as it can move text nodes (tails) and corrupt the output.
    processed_html_str = etree.tostring(body, pretty_print=True, method='html', encoding='utf-8')    

    print("\n--- PROCESSED HTML ---")
    # Replace NBSP with asterisk for debugging
    print(processed_html_str.decode('utf-8').replace('\u00A0', '*'))

