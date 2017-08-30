import copy

from PyQt5.QtWidgets import QGraphicsScene, QGraphicsSceneDragDropEvent, QAbstractItemView, QGraphicsItem
from PyQt5.QtGui import QDropEvent
from PyQt5.QtCore import Qt

from urh.signalprocessing.Message import Message
from urh.signalprocessing.MessageType import MessageType
from urh.signalprocessing.Participant import Participant
from urh.signalprocessing.SimulatorItem import SimulatorItem
from urh.signalprocessing.SimulatorMessage import SimulatorMessage
from urh.signalprocessing.SimulatorGotoAction import SimulatorGotoAction
from urh.signalprocessing.SimulatorProgramAction import SimulatorProgramAction
from urh.signalprocessing.SimulatorProtocolLabel import SimulatorProtocolLabel
from urh.signalprocessing.SimulatorRule import SimulatorRule, SimulatorRuleCondition, ConditionType
from urh.signalprocessing.LabelItem import LabelItem
from urh.signalprocessing.ActionItem import ActionItem, GotoActionItem, ProgramActionItem
from urh.signalprocessing.RuleItem import RuleItem, RuleConditionItem
from urh.signalprocessing.MessageItem import MessageItem
from urh.signalprocessing.ParticipantItem import ParticipantItem
from urh.signalprocessing.GraphicsItem import GraphicsItem
from urh.SimulatorProtocolManager import SimulatorProtocolManager

class SimulatorScene(QGraphicsScene):
    model_to_scene_class_mapping = {
        SimulatorRule: RuleItem,
        SimulatorRuleCondition: RuleConditionItem,
        SimulatorGotoAction: GotoActionItem,
        SimulatorProgramAction: ProgramActionItem,
        SimulatorMessage: MessageItem,
        SimulatorProtocolLabel: LabelItem
    }

    def __init__(self, mode: int, sim_proto_manager: SimulatorProtocolManager, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.sim_proto_manager = sim_proto_manager
        self.tree_root_item = None

        self.participants_dict = {}
        self.participants = []

        self.broadcast_part = self.insert_participant(self.sim_proto_manager.broadcast_part)
        self.not_assigned_part = self.insert_participant(None)
        self.update_participants(refresh=False)

        self.items_dict = {}

        self.on_items_added([item for item in self.sim_proto_manager.rootItem.children])

        self.create_connects()

    def create_connects(self):
        self.sim_proto_manager.participants_changed.connect(self.update_participants)

        self.sim_proto_manager.items_deleted.connect(self.on_items_deleted)
        self.sim_proto_manager.items_updated.connect(self.on_items_updated)
        self.sim_proto_manager.items_moved.connect(self.on_items_moved)
        self.sim_proto_manager.items_added.connect(self.on_items_added)

    def on_items_deleted(self, items):
        for item in items:
            scene_item = self.model_to_scene(item)

            if scene_item in self.items():
                self.removeItem(scene_item)

        self.update_items_dict()
        self.update_view()

    def on_items_updated(self, items):
        scene_items = [self.model_to_scene(item) for item in items]

        for scene_item in scene_items:
            scene_item.refresh()

        self.update_view()

    def on_items_moved(self, items):
        for item in items:
            scene_item = self.model_to_scene(item)
            self.insert_item(scene_item)

        self.update_view()

    def on_items_added(self, items):
        for item in items:
            self.on_item_added(item)

        self.update_view()

    def on_item_added(self, item: SimulatorItem):
        scene_item = self.model_to_scene_class_mapping[type(item)](model_item=item)
        self.insert_item(scene_item)

        # add children to scene ...
        for child in item.children:
            self.on_item_added(child)

    def model_to_scene(self, model_item: SimulatorItem):
        if (model_item is None or
                model_item is self.sim_proto_manager.rootItem):
            return None

        return self.items_dict[model_item]

    def insert_participant(self, participant: Participant):
        scene_part = ParticipantItem(participant)
        scene_part.setVisible(False)
        self.participants.insert(-2, scene_part)
        self.participants_dict[participant] = scene_part
        self.addItem(scene_part)

        return scene_part

    def insert_item(self, item: GraphicsItem):
        parent_scene_item = self.get_parent_scene_item(item)
        item.setParentItem(parent_scene_item)

        self.items_dict[item.model_item] = item

        if item not in self.items():
            self.addItem(item)

        item.update_flags()
        item.refresh()

    def get_parent_scene_item(self, item: GraphicsItem):
        return self.model_to_scene(item.model_item.parent())

    def min_items_width(self):
        width = 0
        items = [item for item in self.items() if isinstance(item, (RuleConditionItem, ActionItem))]

        for item in items:
            if item.labels_width() > width:
                width = item.labels_width()

        return width

    def items_width(self):
        vp = self.visible_participants

        if len(vp) >= 2:
            width = vp[-1].x_pos()
            width -= vp[0].x_pos()
        else:
            width = self.min_items_width()

        return width

    def delete_selected_items(self):
        items = self.selectedItems()
        self.clearSelection()

        self.sim_proto_manager.delete_items([item.model_item for item in items])

    def log_selected_items(self, logging_active: bool):
        items = self.selectedItems()
        self.log_items(items, logging_active)

    def log_items(self, items, logging_active: bool):

        for item in items:
            item.model_item.logging_active = logging_active

        self.sim_proto_manager.items_updated.emit([item.model_item for item in items])

    def log_toggle_selected_items(self):
        items = self.selectedItems()

        for item in items:
            item.model_item.logging_active = not item.model_item.logging_active

        self.sim_proto_manager.items_updated.emit([item.model_item for item in items])

    def log_all_items(self, logging_active: bool):
        self.log_items(self.selectable_items(), logging_active)

    def selectable_items(self):
        return [item for item in self.items() if isinstance(item, GraphicsItem) and
                 item.is_selectable()]

    def move_items(self, items, ref_item, position):
        new_pos, new_parent = self.insert_at(ref_item, position)
        self.sim_proto_manager.move_items(items, new_pos, new_parent)

    def select_all_items(self):
        for item in self.sim_proto_manager.rootItem.children:
            scene_item = self.model_to_scene(item)
            scene_item.select_all()

    def update_numbering(self):
        for item in self.sim_proto_manager.rootItem.children:
            scene_item = self.model_to_scene(item)
            scene_item.update_numbering()

    def update_valid_states(self):
        self.sim_proto_manager.update_valid_states()

    def update_view(self):
        self.update_numbering()
        self.update_valid_states()
        self.arrange_participants()
        self.arrange_items()

        # resize scrollbar
        self.setSceneRect(self.itemsBoundingRect().adjusted(-10, 0 , 0, 0))

    def update_participants(self, refresh=True):
        participants = self.sim_proto_manager.participants

        for key in list(self.participants_dict.keys()):
            if key is None:
                continue

            if key not in participants:
                self.removeItem(self.participants_dict[key])
                self.participants.remove(self.participants_dict[key])
                del self.participants_dict[key]

        for participant in participants:
            if participant in self.participants_dict:
                self.participants_dict[participant].refresh()
            else:
                self.insert_participant(participant)

        if refresh:
            self.update_view()

    def update_items_dict(self):
        sim_items = self.sim_proto_manager.get_all_items()

        for key in list(self.items_dict.keys()):
            if key not in sim_items:
                del self.items_dict[key]

    def get_all_messages(self):
        return [item for item in self.items() if isinstance(item, MessageItem)]

    def select_messages_with_participant(self, participant: ParticipantItem, from_part=True):
        messages = self.get_all_messages()
        self.clearSelection()

        for msg in messages:
            if ((from_part and msg.source is participant) or
                    (not from_part and msg.destination is participant)):
                msg.select_all()

    @property
    def visible_participants(self):
        return [part for part in self.participants if part.isVisible()]

    def arrange_participants(self):
        messages = self.get_all_messages()

        for participant in self.participants:
            if any(msg.source == participant or msg.destination == participant for msg in messages):
                participant.setVisible(True)
            else:
                participant.setVisible(False)
                participant.update_position(x_pos = 30)

        vp = self.visible_participants

        if not vp:
            return

        vp[0].update_position(x_pos = 0)

        for i in range(1, len(vp)):
            curr_participant = vp[i]
            participants_left = vp[:i]

            items = [msg for msg in messages
                    if ((msg.source == curr_participant and msg.destination in participants_left)
                    or (msg.source in participants_left and msg.destination == curr_participant))]

            x_max = vp[i - 1].x_pos()
            x_max += (vp[i - 1].width() + curr_participant.width()) / 2
            x_max += 10

            for msg in items:
                x = msg.width() + 30
                x += msg.source.x_pos() if msg.source != curr_participant else msg.destination.x_pos()

                if x > x_max:
                    x_max = x

            if i == len(vp) - 1:
                if self.min_items_width() > x_max:
                    x_max = self.min_items_width()

            curr_participant.update_position(x_pos = x_max)

    def arrange_items(self):
        x_pos = 0
        y_pos = 30

        for item in self.sim_proto_manager.rootItem.children:
            scene_item = self.model_to_scene(item)
            scene_item.update_position(x_pos, y_pos)
            y_pos += round(scene_item.boundingRect().height())

        for participant in self.participants:
            participant.update_position(y_pos = max(y_pos, 50))

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        if any(item.acceptDrops() for item in self.items(event.scenePos())):
            super().dragMoveEvent(event)
        else:
            event.setAccepted(True)

    def insert_at(self, ref_item, position, insert_rule=False):
        if ref_item:        
            ref_item = ref_item.model_item

        if ref_item is None:
            parent_item = self.sim_proto_manager.rootItem
            insert_position = self.sim_proto_manager.n_top_level_items()
        elif insert_rule:
            parent_item = self.sim_proto_manager.rootItem

            while ref_item.parent() != self.sim_proto_manager.rootItem:
                ref_item = ref_item.parent()

            insert_position = ref_item.get_pos()
        elif isinstance(ref_item, SimulatorRuleCondition):
            if position == QAbstractItemView.OnItem:
                parent_item = ref_item
                insert_position = parent_item.child_count()
            else:
                parent_item = self.sim_proto_manager.rootItem
                insert_position = ref_item.parent().get_pos()
        else:
            parent_item = ref_item.parent()
            insert_position = ref_item.get_pos()

        if position == QAbstractItemView.BelowItem:
            insert_position += 1

        return (insert_position, parent_item)

    def dropEvent(self, event: QDropEvent):
        items = [item for item in self.items(event.scenePos()) if isinstance(item, GraphicsItem) and item.acceptDrops()]
        item = None if len(items) == 0 else items[0]

        indexes = list(event.mimeData().text().split("/")[:-1])

        group_nodes = []
        file_nodes = []
        for index in indexes:
            try:
                row, column, parent = map(int, index.split(","))
                if parent == -1:
                    parent = self.tree_root_item
                else:
                    parent = self.tree_root_item.child(parent)
                node = parent.child(row)
                if node.is_group:
                    group_nodes.append(node)
                else:
                    file_nodes.append(node)
            except ValueError:
                continue

        # Which Nodes to add?
        nodes_to_add = []
        """:type: list of ProtocolTreeItem """
        for group_node in group_nodes:
            nodes_to_add.extend(group_node.children)
        nodes_to_add.extend([file_node for file_node in file_nodes if file_node not in nodes_to_add])
        protocols_to_add = [node.protocol for node in nodes_to_add]

        ref_item = item
        position = None if ref_item is None else item.drop_indicator_position
        self.add_protocols(ref_item, position, protocols_to_add)
        super().dropEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            event.accept()
            return

        super().mousePressEvent(event)

    def add_rule(self, ref_item, position):
        rule = SimulatorRule()
        pos, parent = self.insert_at(ref_item, position, True)
        self.sim_proto_manager.add_items([rule], pos, parent)

        self.add_rule_condition(rule, ConditionType.IF)

    def add_rule_condition(self, rule: SimulatorRule, type: ConditionType):
        rule_condition = SimulatorRuleCondition(type)

        pos = rule.child_count()

        if type is ConditionType.ELSE_IF and rule.has_else_condition():
            pos -= 1

        self.sim_proto_manager.add_items([rule_condition], pos, rule)

    def add_goto_action(self, ref_item, position):
        goto_action = SimulatorGotoAction()
        pos, parent = self.insert_at(ref_item, position, False)
        self.sim_proto_manager.add_items([goto_action], pos, parent)

    def add_program_action(self, ref_item, position):
        program_action = SimulatorProgramAction()
        pos, parent = self.insert_at(ref_item, position, False)
        self.sim_proto_manager.add_items([program_action], pos, parent)

    def add_message(self, plain_bits, pause, message_type, ref_item, position, decoder=None, source=None, destination=None):
        message = self.create_message(destination, plain_bits, pause, message_type, decoder, source)
        pos, parent = self.insert_at(ref_item, position, False)
        self.sim_proto_manager.add_items([message], pos, parent)

    def create_message(self, destination, plain_bits, pause, message_type, decoder, source):
        if destination is None:
            destination = self.sim_proto_manager.broadcast_part

        sim_message = SimulatorMessage(destination=destination, plain_bits=plain_bits, pause=pause,
                        message_type=MessageType(message_type.name), decoder=decoder, source=source)

        for lbl in message_type:
            sim_label = SimulatorProtocolLabel(copy.deepcopy(lbl))
            sim_message.insert_child(-1, sim_label)

        return sim_message

    def clear_all(self):
        self.sim_proto_manager.delete_items([item for item in self.sim_proto_manager.rootItem.children])

    def add_protocols(self, ref_item, position, protocols_to_add: list):
        pos, parent = self.insert_at(ref_item, position)
        messages = []

        for protocol in protocols_to_add:
            for msg in protocol.messages:
                source, destination = self.detect_source_destination(msg)

                messages.append(self.create_message(destination, copy.copy(msg.decoded_bits),
                                msg.pause, msg.message_type, msg.decoder, source))

        self.sim_proto_manager.add_items(messages, pos, parent)

    def get_drag_nodes(self):
        drag_nodes = []
        self.__get_drag_nodes(self.sim_proto_manager.rootItem, drag_nodes)
        return drag_nodes

    def __get_drag_nodes(self, node: SimulatorItem, drag_nodes: list):
        scene_item = self.model_to_scene(node)

        if scene_item and scene_item.isSelected() and scene_item.is_movable():
            drag_nodes.append(scene_item.model_item)

        for child in node.children:
            self.__get_drag_nodes(child, drag_nodes)

    def detect_source_destination(self, message: Message):
        # TODO: use SRC_ADDRESS and DST_ADDRESS labels
        participants = self.sim_proto_manager.participants

        source = None
        destination = self.sim_proto_manager.broadcast_part

        if len(participants) == 2:
            source = participants[0]
        elif len(participants) > 2:
            if message.participant:
                source = message.participant
                #destination = participants[0] if message.participant == participants[1] else participants[1]
            else:
                source = participants[0]
                #destination = participants[1]

        return (source, destination)