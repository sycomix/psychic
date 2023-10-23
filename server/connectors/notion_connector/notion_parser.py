import requests
from models.models import Document, Section
from typing import Dict, List, Optional, Tuple
import json

BASE_URL = "https://api.notion.com"


class NotionParser:
    def __init__(self, access_token: str):
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def notion_get_blocks(self, page_id: str):
        res = requests.get(
            f"{BASE_URL}/v1/blocks/{page_id}/children?page_size=100",
            headers=self.headers,
        )
        res_json = res.json()
        return blocks if (blocks := res_json.get("results")) else []

    def notion_get_page(self, url: str):
        # ID is the last part of the url
        page_id = url.split("/")[-1]
        # If there is a title then the id is the last part separated by dashes
        if "-" in page_id:
            page_id = page_id.split("-")[-1]
        res = requests.get(f"{BASE_URL}/v1/pages/{page_id}", headers=self.headers)
        return res.json()

    def get_documents_in_section(self, page_id) -> List[Dict]:
        unprocessed_pages = [page_id]
        processed_pages = set()
        results: List[Dict] = []
        all_pages = self.notion_search({})

        if not all_pages:
            return []

        while unprocessed_pages:
            # pop the first page
            page_id = unprocessed_pages.pop(0)

            database_ids = []
            for page in all_pages:
                # process the page and add the document to the results
                if page.get("id") == page_id:
                    doc, db_ids_in_page = self.process_page(page)
                    database_ids.extend(db_ids_in_page)
                    results.append(doc)
                    processed_pages.add(page_id)

                # check if the page is a child of page_id
                if (
                    page["parent"]["type"] == "page"
                    and page["parent"]["page_id"] == page_id
                ):
                    if (
                        page.get("id") not in processed_pages
                        and page.get("id") not in unprocessed_pages
                    ):
                        unprocessed_pages.append(page["id"])

            for page in all_pages:
                # check if the parent is a database and with an id in database_ids
                if (
                    page["parent"]["type"] == "database_id"
                    and page["parent"]["database_id"] in database_ids
                ):
                    if (
                        page.get("id") not in processed_pages
                        and page.get("id") not in unprocessed_pages
                    ):
                        unprocessed_pages.append(page["id"])

        return results

    def process_page(self, page) -> Tuple[Optional[Dict], List[str]]:
        object_type = page.get("object")
        object_id = page.get("id")
        url = page.get("url")
        title = ""

        if object_type == "page":
            title = self.parse_title(page)
            blocks = self.notion_get_blocks(object_id)
            html = self.parse_notion_blocks(blocks)
            properties_html = self.parse_properties(page)
            database_ids = self.parse_database_ids(blocks)
            html = f"<div><h1>{title}</h1>{properties_html}{html}</div>"
            return {"title": title, "content": html, "uri": url}, database_ids

        return None

    def notion_search(self, query: Dict):
        print(query)
        res = requests.post(f"{BASE_URL}/v1/search", headers=self.headers, json=query)
        res_json = res.json()
        print(res_json)
        pages = res_json.get("results")
        next_cursor = res_json.get("next_cursor")
        return (pages, next_cursor) if pages else ([], None)

    def parse_property(self, property):
        result = ""
        if property.get("type") == "date":
            if date := property.get("date"):
                result = date.get("start")
        elif property.get("type") == "rich_text":
            if rich_text := property.get("rich_text"):
                result = self.parse_rich_text(rich_text)
        elif property.get("type") == "select":
            if select := property.get("select"):
                result = select.get("name")
        elif property.get("type") == "multi_select":
            if multi_select := property.get("multi_select"):
                result = ", ".join(
                    [item.get("name") for item in multi_select if item.get("name")]
                )
        elif property.get("type") == "number":
            if number := property.get("number"):
                result = number
        elif property.get("type") == "title":
            if title := property.get("title"):
                result = self.parse_rich_text(title)
        elif property.get("type") == "email":
            if email := property.get("email"):
                result = email
        elif property.get("type") == "phone_number":
            if phone_number := property.get("phone_number"):
                result = phone_number
        elif property.get("type") == "url":
            if url := property.get("url"):
                result = url
        elif property.get("type") == "checkbox":
            if checkbox := property.get("checkbox"):
                result = checkbox
        elif property.get("type") == "created_time":
            if created_time := property.get("created_time"):
                result = created_time
        elif property.get("type") == "created_by":
            if created_by := property.get("created_by"):
                result = created_by.get("name")
        elif property.get("type") == "last_edited_time":
            if last_edited_time := property.get("last_edited_time"):
                result = last_edited_time
        elif property.get("type") == "last_edited_by":
            if last_edited_by := property.get("last_edited_by"):
                result = last_edited_by.get("name")
        elif property.get("type") == "formula":
            if formula := property.get("formula"):
                result = formula.get("string")
        else:
            print(f"Property type {property.get('type')} not supported")
            return ""

        return result if result else ""

    def parse_database_ids(self, blocks):
        return [
            block.get("id")
            for block in blocks
            if block.get("type") == "child_database"
        ]

    def parse_properties(self, page):
        html = ""
        properties = page.get("properties")

        # check to see if properties exists and there is more than just the title

        if properties and len(properties) > 1:
            keys = list(properties.keys())

            html = "<table>" + "<thead><tr>"
            for key in keys:
                # exclude the title
                if properties[key].get("title"):
                    continue
                html += f"<th>{key}</th>"
            html += "</tr></thead>"

            html += "<tbody><tr>"
            for key in keys:
                if properties[key].get("title"):
                    continue
                html += f"<td>{self.parse_property(properties[key])}</td>"
            html += "</tr></tbody></table>"
        return html

    def parse_title(self, page):
        title = ""
        properties = page.get("properties")
        if not properties:
            return title

        if title_content := properties.get("title"):
            if len(title_content.get("title")) > 0:
                title = title_content.get("title")[0].get("text").get("content")
        else:
            # page is in a database
            # loop through properties to find the title
            for key in properties:
                if properties[key].get("title"):
                    rich_text = properties[key].get("title")
                    title = self.parse_rich_text(rich_text)
        return title

    def parse_notion_blocks(self, blocks) -> str:
        html = ""
        i = 0
        print(blocks)
        while i < len(blocks):
            block = blocks[i]
            block_type = block.get("type")
            if block_type == "paragraph":
                paragraph_html, new_index = self.parse_paragraph(i, blocks)
                html += paragraph_html
                i = new_index
            elif block_type in ["heading_1", "heading_2", "heading_3"]:
                heading_html, new_index = self.parse_heading(i, blocks)
                html += heading_html
                i = new_index
            elif block_type in ["bulleted_list_item", "numbered_list_item"]:
                list_html, new_index = self.parse_list(i, blocks)
                html += list_html
                i = new_index
            elif block_type == "table":
                table_html, new_index = self.parse_table(i, blocks)
                html += table_html
                i = new_index
            else:
                print(f"Block type {block_type} not supported")
                i += 1
        return html

    def parse_paragraph(self, i, blocks):
        block = blocks[i]
        block_type = block.get("type")
        block_id = block.get("id")
        has_children = block.get("has_children")
        block_content = block.get(block_type)
        rich_text = block_content.get("rich_text")
        assert block_type == "paragraph"

        html = "<p>"
        html += self.parse_rich_text(rich_text)
        if has_children:
            children = self.notion_get_blocks(block_id)
            html += self.parse_notion_blocks(children)
        html += "</p>"
        return html, i + 1

    def parse_heading(self, i, blocks):
        block = blocks[i]
        block_type = block.get("type")
        block_id = block.get("id")
        has_children = block.get("has_children")
        block_content = block.get(block_type)
        rich_text = block_content.get("rich_text")
        assert block_type in ["heading_1", "heading_2", "heading_3"]

        if block_type == "heading_1":
            block_type = "h1"
        elif block_type == "heading_2":
            block_type = "h2"
        else:
            block_type = "h3"

        html = f"<{block_type}>"
        html += self.parse_rich_text(rich_text)
        if has_children:
            children = self.notion_get_blocks(block_id)
            html += self.parse_notion_blocks(children)
        html += f"</{block_type}>"
        return html, i + 1

    def parse_list(self, i, blocks):
        block = blocks[i]
        block_type = block.get("type")
        assert block_type in ["bulleted_list_item", "numbered_list_item"]

        html_list = "ul" if block_type == "bulleted_list_item" else "ol"
        html = f"<{html_list}>"
        while i < len(blocks) and blocks[i].get("type") == block_type:
            block = blocks[i]
            block_id = block.get("id")
            has_children = block.get("has_children")
            block_content = block.get(block_type)
            rich_text = block_content.get("rich_text")

            html += f"<li>{self.parse_rich_text(rich_text)}"
            if has_children:
                children = self.notion_get_blocks(block_id)
                html += self.parse_notion_blocks(children)
            html += "</li>"
            i += 1
        html += f"</{html_list}>"
        return html, i

    def parse_table(self, i, blocks):
        block = blocks[i]
        block_type = block.get("type")
        assert block_type == "table"

        html = "<table>"
        block_id = block.get("id")
        has_children = block.get("has_children")
        block_content = block.get(block_type)

        if has_children:
            children = self.notion_get_blocks(block_id)
            for child in children:
                html += self.parse_table_row(child)
        html += "</table>"
        return html, i + 1

    def parse_table_row(self, block):
        block_type = block.get("type")
        if block_type != "table_row":
            return ""

        html = "<tr>"
        block_content = block.get(block_type)

        cells = block_content.get("cells")
        for rich_text in cells:
            html += "<td>"
            html += self.parse_rich_text(rich_text)
            html += "</td>"
        html += "</tr>"
        return html

    def parse_rich_text(self, rich_text):
        result = []
        for item in rich_text:
            if item.get("type") == "text" and item.get("text"):
                content = item.get("text").get("content")
                link = item.get("text").get("link")
                item_html = ""
                if link and link.get("url"):
                    url = link.get("url")
                    if url.startswith("http"):
                        item_html = f"<a href='{url}'>{content}</a>"
                    elif url.startswith("/"):
                        item_html = (
                            f"<a href='https://www.notion.so{url}'>{content}</a>"
                        )
                else:
                    item_html = content
                result.append(item_html)
            elif item.get("type") == "mention" and item.get("mention"):
                mention = item.get("mention")
                if mention.get("type") == "date":
                    if date := mention.get("date"):
                        result.append(date.get("start"))

        return " ".join(result)
