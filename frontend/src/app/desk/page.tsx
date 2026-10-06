import styles from "./desk.module.css";

export default function DeskHome() {
  return (
    <section className={styles.empty}>
      <p>Pick a case from the queue. Cases ready to publish come first.</p>
    </section>
  );
}
