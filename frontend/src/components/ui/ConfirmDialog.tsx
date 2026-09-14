import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogContentText,
    DialogTitle,
} from "@mui/material";

type ConfirmDialogProps = {
    open: boolean;
    title: string;
    description: React.ReactNode;
    confirmLabel?: string;
    cancelLabel?: string;
    confirmColor?: "primary" | "warning" | "error";
    pending?: boolean;
    onConfirm: () => void;
    onClose: () => void;
};

/** Explicit confirmation for destructive / consequential actions (no window.confirm). */
export function ConfirmDialog({
    open,
    title,
    description,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    confirmColor = "primary",
    pending = false,
    onConfirm,
    onClose,
}: ConfirmDialogProps) {
    return (
        <Dialog open={open} onClose={pending ? undefined : onClose} fullWidth maxWidth="xs">
            <DialogTitle>{title}</DialogTitle>
            <DialogContent>
                <DialogContentText component="div">{description}</DialogContentText>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={pending}>
                    {cancelLabel}
                </Button>
                <Button
                    variant="contained"
                    color={confirmColor}
                    onClick={onConfirm}
                    disabled={pending}
                    autoFocus
                >
                    {confirmLabel}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
