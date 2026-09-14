import { Box, ButtonBase, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { CalendarMonth as CalendarIcon, DragIndicator as DragIcon } from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import type { ProjectTask, ProjectTaskStatus } from "../../../api/projects";
import { formatDateOnly, formatDateTime, humanizeKey } from "../../../utils/formatters";
import { TASK_STATUS_OPTIONS } from "../projectTaskModel";

function Meta({ task }: { task: ProjectTask }) {
    return (
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <Chip label={humanizeKey(task.status)} size="small" variant="outlined" />
            <Chip label={humanizeKey(task.priority)} size="small" variant="outlined" />
            {task.assignee && <Chip label={task.assignee.full_name || task.assignee.email} size="small" variant="outlined" />}
            {task.due_date && (
                <Chip
                    icon={<CalendarIcon fontSize="small" />}
                    label={formatDateOnly(task.due_date)}
                    size="small"
                    variant="outlined"
                    color={task.status !== "done" && new Date(`${task.due_date}T23:59:59`) < new Date() ? "warning" : "default"}
                />
            )}
        </Stack>
    );
}

type BoardProps = {
    task: ProjectTask;
    selected: boolean;
    isDragging: boolean;
    onSelect: () => void;
    onDragStart: () => void;
    onDropBefore: () => void;
    onMove: (status: ProjectTaskStatus) => void;
};

function handleCardKeyDown(event: React.KeyboardEvent, onSelect: () => void) {
    if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect();
    }
}

export function TaskBoardCard({ task, selected, isDragging, onSelect, onDragStart, onDropBefore, onMove }: BoardProps) {
    return (
        <Paper
            role="group"
            aria-label={`Task ${task.title}`}
            draggable
            aria-grabbed={isDragging}
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", task.id);
                event.dataTransfer.effectAllowed = "move";
                onDragStart();
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onDropBefore();
            }}
            sx={(theme) => ({
                p: 1.75,
                borderRadius: 3,
                cursor: "grab",
                border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
                backgroundColor: selected
                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.08)
                    : theme.palette.background.paper,
                "&:focus-visible": {
                    outline: `3px solid ${alpha(theme.palette.primary.main, 0.45)}`,
                    outlineOffset: 2,
                },
            })}
        >
            <Stack spacing={1.25}>
                <ButtonBase
                    onClick={onSelect}
                    aria-pressed={selected}
                    aria-label={`Select task ${task.title}`}
                    sx={(theme) => ({
                        width: "100%",
                        justifyContent: "space-between",
                        textAlign: "left",
                        borderRadius: 1,
                        px: 0.25,
                        "&:focus-visible": {
                            outline: `3px solid ${alpha(theme.palette.primary.main, 0.45)}`,
                            outlineOffset: 2,
                        },
                    })}
                >
                    <Typography variant="subtitle2">{task.title}</Typography>
                    <DragIcon fontSize="small" color="action" aria-hidden="true" />
                </ButtonBase>
                <Typography variant="body2" color="text.secondary">{task.description || "No task notes yet."}</Typography>
                <Meta task={task} />
                <TextField
                    select
                    size="small"
                    label="Move to"
                    value=""
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => {
                        event.stopPropagation();
                        onMove(event.target.value as ProjectTaskStatus);
                    }}
                    fullWidth
                    SelectProps={{ displayEmpty: true, renderValue: () => "Choose column" }}
                    inputProps={{ "aria-label": `Move ${task.title} to another column` }}
                >
                    {TASK_STATUS_OPTIONS.filter((option) => option.value !== task.status).map((option) => (
                        <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                    ))}
                </TextField>
            </Stack>
        </Paper>
    );
}

export function TaskListCard({ task, selected, onSelect }: { task: ProjectTask; selected: boolean; onSelect: () => void }) {
    return (
        <Paper
            role="button"
            tabIndex={0}
            aria-pressed={selected}
            aria-label={`Select task ${task.title}`}
            onClick={onSelect}
            onKeyDown={(event) => handleCardKeyDown(event, onSelect)}
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                cursor: "pointer",
                border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
                backgroundColor: selected
                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.06)
                    : theme.palette.background.paper,
                "&:focus-visible": {
                    outline: `3px solid ${alpha(theme.palette.primary.main, 0.45)}`,
                    outlineOffset: 2,
                },
            })}
        >
            <Stack spacing={1.25}>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                    <Box>
                        <Typography variant="subtitle1">{task.title}</Typography>
                        <Typography variant="body2" color="text.secondary">{task.description || "No task notes yet."}</Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">Updated {formatDateTime(task.updated_at)}</Typography>
                </Stack>
                <Meta task={task} />
            </Stack>
        </Paper>
    );
}
